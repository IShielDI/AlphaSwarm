"""Deterministic validation of the Task 1 fixes in run_structured_agent.

No live network: we monkeypatch `llm_client._CHAT.run` to simulate each
provider attempt, then assert the corrective control-flow:

  1. Nested-fallback fix: an OpenRouter 429 WHILE the Google fallback is
     already active is logged distinctly and does NOT re-trigger the Google
     fallback (branch on effective_provider, not the original provider).
  2. Structured-output-unsupported fix: the capability error is granted one
     extra attempt and does not spend a content/schema retry.
  3. The sticky `_google_quota_exhausted` latch is intentionally documented
     as never being reset (no expiry logic per task).

Run with:  python tests/test_llm_client_fallback.py
"""

from __future__ import annotations

import io
import logging
import os
import unittest

from alphaswarm.agents import llm_client
from alphaswarm.agents.llm_client import (
    AgentSchemaError,
    LLMError,
    StructuredOutputUnsupportedError,
    run_structured_agent,
)

_NO_TRADE = '"NO_TRADE"'  # JSON-encoded string, as a real model would emit it.


class _FakeRun:
    """Replaces llm_client._CHAT.run with scripted per-call behavior.

    Each element of `script` describes one call: a raise-class/exception to
    raise, or a string to return. We key off the transport function that the
    runner actually dispatched, so the fallback (effective_provider switch)
    is verified by which transport got called.
    """

    def __init__(self, by_transport):
        # by_transport: {transport_name: [behavior, ...]}; behavior is either
        # a BaseException to raise or a str to return.
        self.by_transport = by_transport
        self.calls: list[tuple[str, str]] = []  # (transport, sentinel)

    def __call__(self, fn, model, system_prompt, user_prompt, temperature):
        name = fn.__name__
        sentinel = "raise" if name in self.by_transport else "return"
        self.calls.append((name, sentinel))
        queue = self.by_transport.get(name, [])
        behavior = queue.pop(0) if queue else _NO_TRADE
        if isinstance(behavior, BaseException):
            raise behavior
        return behavior


def _capture_logs():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.WARNING)
    logger = logging.getLogger("alphaswarm.agents.llm_client")
    logger.setLevel(logging.WARNING)
    logger.addHandler(handler)
    return buf, handler, logger


class TestFallbackFix(unittest.TestCase):
    def setUp(self) -> None:
        llm_client._google_quota_exhausted = False

    def tearDown(self) -> None:
        llm_client._google_quota_exhausted = False

    # ------------------------------------------------------------------
    # Fix 1: nested-fallback misdiagnosis
    # ------------------------------------------------------------------
    def test_openrouter_429_while_fallback_active_is_distinct(self):
        buf, handler, logger = _capture_logs()
        self.addCleanup(logger.removeHandler, handler)
        script = {
            # attempt 1 -> Gemini quota (triggers fallback switch)
            "_gemini_chat": [LLMError("Gemini HTTP 429: quota exhausted")],
            # attempt 2 -> OpenRouter 429 WHILE fallback is active
            "_openrouter_chat": [LLMError("OpenRouter HTTP 429: rate limited")],
        }
        fake = _FakeRun(script)
        original = llm_client._CHAT.run
        llm_client._CHAT.run = fake
        self.addCleanup(setattr, llm_client._CHAT, "run", original)

        with self.assertRaises(AgentSchemaError):
            run_structured_agent(
                "test", "sys", "usr", "some/model", provider="google",
                max_attempts=2,
            )

        log_text = buf.getvalue()
        # Exactly one Google-fallback switch, and exactly one distinct
        # OpenRouter-fallback rate-limit note (not a second Gemini switch).
        self.assertEqual(log_text.count("Gemini 429 -- switching"), 1)
        self.assertEqual(log_text.count("OpenRouter fallback rate-limited"), 1)
        # The transport dispatches: gemini (attempt 1) then openrouter (attempt 2).
        self.assertEqual(
            [name for name, _ in fake.calls], ["_gemini_chat", "_openrouter_chat"]
        )
        # The sticky latch was set by the google quota.
        self.assertTrue(llm_client._google_quota_exhausted)

    # ------------------------------------------------------------------
    # Fix 2: StructuredOutputUnsupportedError must not eat retry budget
    # ------------------------------------------------------------------
    def test_capability_error_gets_one_extra_attempt(self):
        script = {
            "_gemini_chat": [
                StructuredOutputUnsupportedError("Gemini cannot do JSON output"),
                "this is not json at all",  # content failure on attempt 2
                _NO_TRADE,                   # success on the extra attempt 3
            ],
        }
        fake = _FakeRun(script)
        original = llm_client._CHAT.run
        llm_client._CHAT.run = fake
        self.addCleanup(setattr, llm_client._CHAT, "run", original)

        result = run_structured_agent(
            "strategist", "sys", "usr", "g/model", provider="google",
            max_attempts=2,
        )
        # Without the fix, max_attempts=2 would raise AgentSchemaError after
        # the capability error + one content failure. With the fix the
        # capability fact is granted an extra attempt and the call succeeds.
        self.assertEqual(result, "NO_TRADE")
        self.assertEqual(len(fake.calls), 3)

    # ------------------------------------------------------------------
    # Fix 3: sticky latch is documented, not expired
    # ------------------------------------------------------------------
    def test_latch_is_documented_as_intentional_and_sticky(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "alphaswarm", "agents", "llm_client.py",
        )
        with open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertIn("_google_quota_exhausted latches for the life of the process", src)
        self.assertNotIn("time.time()", src.split("_google_quota_exhausted")[1][:400])


if __name__ == "__main__":
    unittest.main(verbosity=2)

