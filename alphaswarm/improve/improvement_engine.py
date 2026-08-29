"""Improvement Engine -- ONE hypothesis from the log, reviewed by the Mentor.

Mechanism demo only (02_TRD / user instruction): with the current sample
size (a handful of observations) NOTHING here is statistically validated.
The generated hypothesis and the Mentor's review are both explicitly
labeled with a sample-size caveat, and the review schema REQUIRES the
reviewer to state that caveat.

Flow: imperfection_log.per_agent_summary() -> one hypothesis (deterministic
selection: strongest signal in the log, not an LLM guess) -> Mentor reviews
accept/reject under the HYPOTHESIS_REVIEW_SCHEMA.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..agents.llm_client import run_structured_agent
from ..agents.mentor import Mentor
from . import imperfection_log

logger = logging.getLogger(__name__)

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


def run_cycle(path: str | None = None) -> Dict[str, Any] | None:
    """Full demo cycle: log -> one hypothesis -> Mentor review."""
    hyp = generate_hypothesis(path)
    if hyp is None:
        logger.warning("imperfection log has no signal; skipping cycle")
        return None
    review = review_hypothesis(hyp)
    return {"hypothesis": hyp, "mentor_review": review}
