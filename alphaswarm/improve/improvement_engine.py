"""Improvement Engine -- ONE hypothesis from the log, reviewed by the Mentor.

Mechanism demo only (02_TRD / user instruction): with the current sample
size (a handful of observations) NOTHING here is statistically validated.
The generated hypothesis and the Mentor's review are both explicitly
labeled with a sample-size caveat, and the review schema REQUIRES the
reviewer to state that caveat.

Flow: imperfection_log.per_agent_summary() -> one hypothesis (deterministic
selection: strongest signal in the log, not an LLM guess) -> Mentor reviews
accept/reject under the HYPOTHESIS_REVIEW_SCHEMA -> version record appended to
versions.jsonl (ACCEPTED or REJECTED, with config_snapshot + previous_version
for rollback -- reading the prior entry is sufficient to revert, no separate
infrastructure needed).

Version records are part of the auditable history: accepted hypotheses are
promoted, rejected ones are logged with "REJECTED" and the reason.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..agents.llm_client import run_structured_agent
from ..agents.mentor import Mentor
from . import imperfection_log

logger = logging.getLogger(__name__)

# versions.jsonl lives at the project root, alongside imperfections_log.jsonl
# and decisions.jsonl (path resolution matches imperfection_log.LOG_PATH).
VERSIONS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    os.pardir, "versions.jsonl"
)


def _now() -> str:
    """UTC timestamp, seconds precision (mirrors imperfection_log._now)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

REVIEW_SYSTEM_PROMPT = """You are the Mentor reviewing ONE improvement hypothesis \
proposed by the Improvement Engine. You did not generate it; your job is to judge \
whether it is worth acting on.

RULES:
- The evidence base is tiny (a handful of trades at most). You MUST reject any \
hypothesis that calls for changing prompts, models, or risk parameters outright; \
acceptable hypotheses are observation-collection or instrumentation proposals \
("log X next time", "watch for Y").
- You MUST set sample_size_caveat to a specific statement of why the current \
sample size is too small for statistical validation.
- verdict "accept" means: worth tracking/instrumenting, NOT worth changing behavior.
- verdict "reject" means: not even worth tracking, with reasoning.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) \
with EXACTLY these fields and no others:
{
  "verdict": "accept | reject",
  "reasoning": "<why, referencing the evidence quality>",
  "conditions": ["<what must be observed before acting on this hypothesis>", ...],
  "sample_size_caveat": "<specific statement of the n-too-small limitation>"
}"""


def generate_hypothesis(path: str | None = None) -> Dict[str, Any] | None:
    """Deterministically build ONE hypothesis from the log's strongest signal."""
    summary = imperfection_log.per_agent_summary(path)
    candidates = []
    for agent, s in summary.items():
        n = s.get("n_observations", 0)
        if n < 1:
            continue
        weaknesses = [w for w in (s.get("weaknesses") or [])
                      if w and "none observed" not in w.lower()]
        # Rank: agents with an actual observed weakness first, then more observations.
        candidates.append((0 if weaknesses else 1, -n, agent, s, weaknesses))
    if not candidates:
        return None
    candidates.sort()
    _, _, agent, s, weak = candidates[0]
    strengths = s.get("strengths") or ["unspecified"]
    return {
        "agent": agent,
        "hypothesis": (
            f"{agent}'s weak area ({'; '.join(weak)}) may recur under conditions "
            f"similar to those already observed. Instrument future decision cycles "
            f"to log this agent's output on that dimension explicitly, so the "
            f"hypothesis can be confirmed or refuted as sample size grows. "
            f"Known strength ({'; '.join(strengths)}) should not be modified."
        ),
        "evidence": {
            "n_observations": s.get("n_observations"),
            "weak_areas": weak,
            "strength_areas": strengths,
        },
        "proposed_action": (
            "add explicit logging/monitoring for this dimension in future cycles; "
            "NO change to prompts, models, or risk parameters at this sample size"
        ),
    }


def review_hypothesis(hypothesis: Dict[str, Any], model: str | None = None) -> Dict[str, Any]:
    """Send ONE hypothesis to the Mentor for accept/reject review."""
    mentor = Mentor()
    user = (
        f"Improvement hypothesis from the Improvement Engine:\n{hypothesis}\n\n"
        "Review it under the strict rules in your instructions. Return only the "
        "JSON object with the exact required fields."
    )
    return run_structured_agent(
        "hypothesis_review", REVIEW_SYSTEM_PROMPT, user, model or mentor._model
    )


# ---------------------------------------------------------------------------
# Version recording (auditable history of accepted/rejected hypotheses)
# ---------------------------------------------------------------------------


def load_versions(path: str | None = None) -> List[Dict[str, Any]]:
    """Load all version records from the JSONL file (empty list if missing)."""
    p = path or VERSIONS_PATH
    if not os.path.exists(p):
        return []
    out: List[Dict[str, Any]] = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _next_version_number(path: str | None = None) -> int:
    """Return the next version number by reading the last record."""
    records = load_versions(path)
    if not records:
        return 1
    return max(r["version"] for r in records) + 1


def record_version(
    hypothesis: Dict[str, Any],
    review: Dict[str, Any],
    path: str | None = None,
) -> Dict[str, Any]:
    """Append a version record to versions.jsonl after Mentor review.

    Handles both accept and reject verdicts:
      - accept -> promotion_decision "ACCEPTED"
      - reject -> promotion_decision "REJECTED"

    Each record includes:
      - version: next integer (increment from last record)
      - timestamp
      - promotion_decision: ACCEPTED | REJECTED
      - change_description: the proposed change (hypothesis.proposed_action)
      - triggering_imperfection: which recurring imperfection triggered it
        (hypothesis evidence weak_areas)
      - agent: the agent whose weakness triggered the hypothesis
      - mentor_notes: reasoning, conditions, sample_size_caveat
      - hypothesis: the full hypothesis dict
      - review: the full Mentor review dict
      - config_snapshot: relevant config/prompt text for THIS version
      - previous_version: snapshot of the prior record's config_snapshot
        (for rollback -- reading the prior entry is sufficient to revert;
        null when this is the first version)

    Rejected experiments are part of the auditable history -- they are logged
    with promotion_decision "REJECTED" and the reason, per the original design.
    """
    version_num = _next_version_number(path)
    records = load_versions(path)
    previous_version: Optional[Dict[str, Any]] = None
    if records:
        prev = records[-1]
        previous_version = {
            "version": prev["version"],
            "config_snapshot": prev.get("config_snapshot", {}),
        }

    verdict = (review.get("verdict") or "").strip().lower()
    if verdict == "accept":
        promotion_decision = "ACCEPTED"
    elif verdict == "reject":
        promotion_decision = "REJECTED"
    else:
        promotion_decision = verdict.upper() if verdict else "UNKNOWN"

    evidence = hypothesis.get("evidence", {})
    change_description = hypothesis.get("proposed_action", "")
    triggering_imperfection = evidence.get("weak_areas", [])

    config_snapshot = {
        "review_system_prompt": REVIEW_SYSTEM_PROMPT,
        "proposed_action": change_description,
        "hypothesis_text": hypothesis.get("hypothesis", ""),
        "agent": hypothesis.get("agent", ""),
    }

    record: Dict[str, Any] = {
        "version": version_num,
        "timestamp": _now(),
        "promotion_decision": promotion_decision,
        "change_description": change_description,
        "triggering_imperfection": triggering_imperfection,
        "agent": hypothesis.get("agent", ""),
        "mentor_notes": {
            "reasoning": review.get("reasoning", ""),
            "conditions": review.get("conditions", []),
            "sample_size_caveat": review.get("sample_size_caveat", ""),
        },
        "hypothesis": hypothesis,
        "review": review,
        "config_snapshot": config_snapshot,
        "previous_version": previous_version,
    }

    p = path or VERSIONS_PATH
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    logger.info(
        "version record %d written to %s (decision=%s)",
        version_num, p, promotion_decision,
    )
    return record


def run_cycle(path: str | None = None) -> Dict[str, Any] | None:
    """Full demo cycle: log -> one hypothesis -> Mentor review -> version record."""
    hyp = generate_hypothesis(path)
    if hyp is None:
        logger.warning("imperfection log has no signal; skipping cycle")
        return None
    review = review_hypothesis(hyp)
    version_rec = record_version(hyp, review)
    return {
        "hypothesis": hyp,
        "mentor_review": review,
        "version_record": version_rec,
    }
