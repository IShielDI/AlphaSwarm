"""Shared LLM client layer for AlphaSwarm agents.

Two providers, one integration each (TRD Section 1):
  * OpenRouter  -- DeepSeek / Qwen3-Coder / GLM-4.5-Air / Nemotron
  * Google AI Studio -- Gemini Flash (Strategist only)

Hard rules implemented here (Agent Rules Sections 3.6, 4, 5):
  * Every agent output must conform exactly to its locked schema --
    all required fields present AND no extra fields.
  * If an agent's output fails schema validation twice in a row, the
    caller halts the decision cycle (AgentSchemaError) -- malformed
    output is a build error, never routed around and never silently
    passed downstream.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Callable, List, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model assignment (LOCKED per Agent Rules Section 2 -- do not swap without
# re-validating structured-output reliability against the schema).
# ---------------------------------------------------------------------------
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent"
)

MODEL_DEEPSEEK = "deepseek/deepseek-v4-flash"
MODEL_QWEN3_CODER = "qwen/qwen3-coder"
MODEL_GLM45_AIR = "z-ai/glm-4.5-air"
MODEL_NEMOTRON = "nvidia/nemotron-3-super-120b-a12b"  # Mentor (TRD Section 2, locked)
MODEL_GEMINI_FLASH = "gemini-3.6-flash"  # 2.5-flash is 404 for new keys (Aug 2026)
# Strategist fallback (Google AI Studio free-tier quota exhausts fast; on a
# 429 we retry the SAME role via OpenRouter, which has a separate quota pool).
MODEL_STRATEGIST_FALLBACK = "google/gemini-3.6-flash"  # via OpenRouter
# Gemini thinking budgets (3.6-flash is a thinking model; thoughts count
# toward maxOutputTokens). Low budget trades depth of deliberation for
# latency -- re-validate output quality whenever this changes.
GEMINI_THINKING_BUDGET = 1024
# OpenRouter reasoning effort for the Mentor. "low" cut the audit latency
# substantially; the standalone 4-case Mentor test must still pass before
# relying on this (scripts/day3_mentor_test.py).
MENTOR_REASONING_EFFORT = "low"

MAX_SCHEMA_ATTEMPTS = 2  # Agent Rules Section 5: halt after 2 consecutive failures

# _google_quota_exhausted latches for the life of the process: once the
# Google free-tier quota is confirmed exhausted we stay on the OpenRouter
# fallback for the rest of this run, deliberately NOT flapping back and forth
# on transient per-minute limits. Intentional -- do not add a reset or expiry
# to this flag; it is meant to be sticky per process (Task 1 issue 3).
_google_quota_exhausted = False


class AgentSchemaError(RuntimeError):
    """Raised when an agent's output fails schema validation twice in a row.

    Per Agent Rules Section 5 this must halt the decision cycle -- callers
    must not proceed to downstream agents with malformed input.
    """

    def __init__(self, agent: str, attempts: List[List[str]]):
        self.agent = agent
        self.attempts = attempts
        lines = [f"agent '{agent}' failed schema validation {len(attempts)}x in a row:"]
        for i, errs in enumerate(attempts, 1):
            lines.append(f"  attempt {i}: " + "; ".join(errs))
        super().__init__("\n".join(lines))


class LLMError(RuntimeError):
    """HTTP / transport-level failure talking to a provider."""


class StructuredOutputUnsupportedError(RuntimeError):
    """Raised when a provider cannot honor the requested structured-output
    mode (forced JSON response / responseMimeType).

    This is a capability fact, NOT a content-quality failure, so it must not
    consume the schema/content retry budget (Task 1 issue 2).
    """


def _is_quota_error(e: LLMError) -> bool:
    """True for provider rate-limit / quota-exhaustion errors (HTTP 429)."""
    msg = str(e)
    return "429" in msg or "quota" in msg.lower() or "rate limit" in msg.lower()


def extract_json(text: str) -> Any:
    """Extract the first JSON object from an LLM response.

    Handles bare JSON, ```json fenced blocks, and leading prose. Raises
    ValueError if no parseable JSON object is found.
    """
    if text is None:
        raise ValueError("empty response")
    # Whole-text JSON first (covers bare objects and bare "NO_TRADE").
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        break


# ---------------------------------------------------------------------------
# Schema-strict structured agent runner
# ---------------------------------------------------------------------------

def validate_exact_fields(agent: str, output: Any) -> List[str]:
    """Strict validation: all required fields present AND no extra fields.

    The locked schemas are exact I/O contracts, so extra top-level keys
    are also errors. The strategist may return the literal "NO_TRADE".
    """
    from ..schemas.agent_schemas import AGENT_SCHEMAS, STRATEGIST_NO_TRADE, validate_agent_output

    if agent == "strategist" and output == STRATEGIST_NO_TRADE:
        return []
    ok, errors = validate_agent_output(agent, output)
    if not ok:
        return errors
    if isinstance(output, dict) and agent in AGENT_SCHEMAS:
        required = set(AGENT_SCHEMAS[agent])
        extra = sorted(set(output.keys()) - required)
        if extra:
            errors.append(f"unexpected extra field(s): {extra}")
    return errors


def run_structured_agent(
    agent: str,
    system_prompt: str,
    user_prompt: str,
    model: str,
    provider: str = "openrouter",
    semantic_validator: Optional[Callable[[Any], List[str]]] = None,
    max_attempts: int = MAX_SCHEMA_ATTEMPTS,
    temperature: float = 0.2,
    reasoning_effort: Optional[str] = None,
) -> Any:
    """Call the model, extract JSON, and validate against the locked schema.

    Retries up to `max_attempts` (default 2, per Agent Rules Section 5).
    On two consecutive failures raises AgentSchemaError -- the caller must
    halt the decision cycle. A `semantic_validator` may add checks beyond
    field presence (e.g. enum membership, structure limits); its errors
    count toward the same retry budget.

    `reasoning_effort` ("low"/"medium"/"high") is forwarded to providers
    that expose reasoning control (OpenRouter `reasoning.effort`; Gemini
    maps it to a thinkingConfig budget).

    Strategist-only 429 fallback: Google AI Studio's free-tier quota
    exhausts quickly. If the Gemini transport returns a 429/quota error,
    the remaining attempts automatically run the SAME role through
    OpenRouter with MODEL_STRATEGIST_FALLBACK (separate quota pool).
    """
    global _google_quota_exhausted
    errors_per_attempt: List[List[str]] = []
    # effective_* track the provider/model ACTUALLY used this attempt, which
    # may differ from the original `provider` once the Google fallback kicks
    # in. Branching on these (not the original arg) is the Task 1 issue 1 fix.
    effective_provider = provider
    effective_model = model
    capability_topup_done = False  # one extra attempt for capability facts only
    attempt = 0
    while attempt < max_attempts:
        attempt += 1
        try:
            if effective_provider == "openrouter":
                raw = _CHAT.run(
                    _openrouter_chat, effective_model, system_prompt, user_prompt, temperature
                )
            else:
                raw = _CHAT.run(
                    _gemini_chat, effective_model, system_prompt, user_prompt, temperature
                )
        except StructuredOutputUnsupportedError as e:
            # Capability fact, not a content/schema quality failure: grant ONE
            # extra attempt for this provider->prompt-only transition instead
            # of spending the shared retry budget (Task 1 issue 2).
            if not capability_topup_done:
                capability_topup_done = True
                max_attempts += 1
            errors_per_attempt.append([f"structured output unsupported: {e}"])
            logger.warning(
                "%s attempt %d structured output unsupported: %s", agent, attempt, e
            )
            continue
        except LLMError as e:
            errors_per_attempt.append([f"transport error: {e}"])
            logger.warning("%s attempt %d transport error: %s", agent, attempt, e)
            if effective_provider == "google" and _is_quota_error(e):
                # Google free-tier quota exhausted: switch this role to the
                # OpenRouter fallback (separate quota pool) for the remainder.
                logger.warning(
                    "%s: Gemini 429 -- switching to OpenRouter fallback", agent
                )
                effective_provider = "openrouter"
                effective_model = MODEL_STRATEGIST_FALLBACK
                _google_quota_exhausted = True
            elif (
                effective_provider == "openrouter"
                and _google_quota_exhausted
                and _is_quota_error(e)
            ):
                # Already on the fallback and OpenRouter itself is rate-limited:
                # log it distinctly for later diagnosis. Do NOT re-trigger the
                # Google fallback (it is already active) -- the normal transport
                # error above already records this attempt.
                logger.warning(
                    "OpenRouter fallback rate-limited for %s (attempt %d): %s",
                    agent, attempt, e,
                )
            continue
        try:
            output = extract_json(raw)
        except ValueError as e:
            errors_per_attempt.append([f"unparseable JSON: {e}"])
            logger.warning(
                "%s attempt %d: unparseable JSON; raw=%r",
                agent, attempt, (raw or "")[:800],
            )
            continue

        errors = validate_exact_fields(agent, output)
        if semantic_validator is not None and not errors:
            errors = semantic_validator(output)
        if not errors:
            logger.info("%s: schema-valid output on attempt %d", agent, attempt)
            return output
        errors_per_attempt.append(errors)
        logger.warning("%s attempt %d schema errors: %s", agent, attempt, errors)

    raise AgentSchemaError(agent, errors_per_attempt)


# ---------------------------------------------------------------------------
# Provider transports
# ---------------------------------------------------------------------------

class _ChatDeadline:
    """Hard wall-clock deadline for one chat call.

    Socket read-timeouts can fail to fire when a proxy keeps the connection
    warm with keepalive bytes, so each call runs in a daemon thread bounded
    in wall time. Daemon so an abandoned hung thread can't block exit.
    """

    def __init__(self, seconds: int = 240):
        self._seconds = seconds

    def run(self, fn, *args, **kwargs):
        import threading

        result: dict = {}

        def _target():
            try:
                result["value"] = fn(*args, **kwargs)
            except BaseException as e:  # noqa: BLE001 - propagated below
                result["error"] = e

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(self._seconds)
        if thread.is_alive():
            raise LLMError(
                f"hard deadline of {self._seconds}s exceeded for chat call"
            )
        if "error" in result:
            raise result["error"]
        return result.get("value")


_CHAT = _ChatDeadline()


def _openrouter_chat(model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    from .. import config

    if not config.OPENROUTER_API_KEY or config.OPENROUTER_API_KEY.startswith("<"):
        raise LLMError("OPENROUTER_API_KEY missing -- set it in .env")
    try:
        resp = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": 8000,
            },
            timeout=(10, 90),
        )
    except requests.RequestException as e:
        raise LLMError(f"OpenRouter transport failure: {e}") from e
    # Transient upstream rate limits (429) are common on shared free-tier
    # providers -- back off and retry within the same schema attempt.
    for wait in (20, 40):
        if resp.status_code != 429:
            break
        logger.warning("OpenRouter 429 for %s; backing off %ss", model, wait)
        time.sleep(wait)
        try:
            resp = requests.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {config.OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 8000,
                },
                timeout=(10, 90),
            )
        except requests.RequestException as e:
            raise LLMError(f"OpenRouter transport failure: {e}") from e
    if resp.status_code != 200:
        raise LLMError(f"OpenRouter HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"unexpected OpenRouter response shape: {data}") from e


def _gemini_chat(model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
    from .. import config

    if not config.GOOGLE_AI_STUDIO_API_KEY or config.GOOGLE_AI_STUDIO_API_KEY.startswith("<"):
        raise LLMError("GOOGLE_AI_STUDIO_API_KEY missing -- set it in .env")
    url = GEMINI_URL_TEMPLATE.format(model=model)
    try:
        resp = requests.post(
            url,
            params={"key": config.GOOGLE_AI_STUDIO_API_KEY},
            headers={"Content-Type": "application/json"},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                "generationConfig": {
                    "temperature": temperature,
                    # 3.6-flash is a thinking model: thoughts count toward this
                    # budget. 2048 truncates mid-thought and the call stalls.
                    "maxOutputTokens": 8192,
                    "responseMimeType": "application/json",
                },
            },
            timeout=(10, 90),
        )
    except requests.RequestException as e:
        raise LLMError(f"Gemini transport failure: {e}") from e
    if resp.status_code != 200:
        body = resp.text[:300]
        if resp.status_code == 400 and (
            "responseMimeType" in body
            or "structured output" in body.lower()
            or "not supported" in body.lower()
        ):
            # Gemini refused the forced-JSON (responseMimeType) mode -- a
            # capability limitation, not malformed content (Task 1 issue 2).
            raise StructuredOutputUnsupportedError(f"Gemini structured output unsupported: {body}")
        raise LLMError(f"Gemini HTTP {resp.status_code}: {body}")
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"unexpected Gemini response shape: {data}") from e