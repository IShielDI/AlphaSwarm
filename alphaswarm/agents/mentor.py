"""Mentor (Agent Rules Section 1: owns criticism, audit, targeted feedback).

Model: Nemotron via OpenRouter (locked -- highest-stakes structured-output
requirement in the system per TRD Section 4).

Output: exact MENTOR_SCHEMA (overall_decision + imperfections array with
component / owner / severity / reason / action / invalidate_downstream).

Per Agent Rules Section 4, the prompt REQUIRES component-by-component
decomposition before the overall_decision -- a holistic "looks fine" is
not acceptable. Per Section 3.4, corrections are routed per-component to
the responsible agent (see orchestrator._OWNERSHIP for the routing map).

Standalone schema validation (scripts/day3_mentor_test.py) must pass on
multiple sample proposals BEFORE this agent is wired into the loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from ..schemas.agent_schemas import MENTOR_DECISIONS
from .llm_client import MODEL_NEMOTRON, run_structured_agent

logger = logging.getLogger(__name__)

# Owners the Mentor may assign imperfections to (Agent Rules Section 1 table).
VALID_OWNERS = [
    "market_agent",
    "volatility_agent",
    "options_agent",
    "portfolio_agent",
    "strategist",
    "none",  # imperfection attributable to process, not one agent
]

SYSTEM_PROMPT = """You are the Mentor in a multi-agent trading system. You own \
criticism, audit, and targeted feedback routing. You do NOT produce trade proposals, \
market analysis, or any other agent's output.

AUDIT PROCEDURE (mandatory, in order):
1. Check the MARKET AGENT output: is the regime/bias call supported by its own evidence? \
Any internal contradiction?
2. Check the VOLATILITY AGENT output: is the IV assessment consistent with the numbers \
(IV vs realized vol, term structure)?
3. Check the OPTIONS AGENT output: do the contract candidates use real symbols/strikes, \
consistent Greeks, honest liquidity assessment? Are structures limited to vertical \
credit spreads?
4. Check the PORTFOLIO AGENT output: is the recommendation consistent with the \
exposure/conflict data?
5. Check the STRATEGIST proposal: does it faithfully synthesize the four outputs? Are \
strikes/credit consistent with the Options Agent's surface? Are the entry/exit/\
invalidation conditions actionable? Are reasons_not_to_trade honestly weighed rather \
than ignored?

You MUST go through this component-by-component breakdown BEFORE rendering an \
overall_decision. A holistic "looks fine" or "looks bad" without the component breakdown \
is not acceptable. List one imperfection entry per component that has a problem \
(empty list only if genuinely nothing is wrong). The overall_decision must follow from \
the imperfections: no material imperfections -> APPROVE; fixable problems -> REVISE; \
fundamental flaws (fabricated data, scope violations, contradictions that cannot be \
revised) -> REJECT; genuinely missing information -> WAIT.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) with \
EXACTLY these fields and no others:
{
  "overall_decision": "APPROVE | REVISE | REJECT | WAIT",
  "imperfections": [
    {
      "component": "<short name of the flawed component, e.g. 'directional bias', 'liquidity assessment'>",
      "owner": "market_agent | volatility_agent | options_agent | portfolio_agent | strategist | none",
      "severity": "low | medium | high",
      "reason": "<what is wrong and why it matters>",
      "action": "<the specific correction the owner should perform>",
      "invalidate_downstream": <true if components built on top of this one must be reconsidered>
    }
  ]
}"""


def _semantic_validate(out: Dict[str, Any]) -> List[str]:
    """Beyond-schema checks: owner enum, decision/imperfections consistency."""
    errors: List[str] = []
    for imp in out.get("imperfections", []):
        owner = imp.get("owner")
        if owner not in VALID_OWNERS:
            errors.append(f"imperfection owner {owner!r} not one of {VALID_OWNERS}")
        action = imp.get("action")
        if isinstance(action, str) and len(action.strip()) < 5:
            errors.append("imperfection action must be a specific correction instruction")
    decision = out.get("overall_decision")
    if decision in ("REVISE", "REJECT") and not out.get("imperfections"):
        errors.append(f"{decision} requires at least one imperfection")
    if decision not in MENTOR_DECISIONS:  # defensive; schema layer also checks
        errors.append(f"overall_decision must be one of {MENTOR_DECISIONS}")
    return errors


class Mentor:
    def __init__(self, model: str = MODEL_NEMOTRON):
        self._model = model

    def audit(
        self,
        ticker: str,
        proposal: Dict[str, Any],
        market_analysis: Dict[str, Any],
        volatility_analysis: Dict[str, Any],
        options_analysis: Dict[str, Any],
        portfolio_analysis: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Audit one Strategist proposal against its four Layer-1 inputs.

        Returns the exact MENTOR_SCHEMA dict (raises AgentSchemaError after
        the retry cap -- malformed mentor output must halt the cycle, per
        Agent Rules Section 5).
        """
        user = (
            f"Underlying: {ticker}\n\n"
            f"MARKET AGENT output:\n{market_analysis}\n\n"
            f"VOLATILITY AGENT output:\n{volatility_analysis}\n\n"
            f"OPTIONS AGENT output:\n{options_analysis}\n\n"
            f"PORTFOLIO AGENT output:\n{portfolio_analysis}\n\n"
            f"STRATEGIST PROPOSAL under audit:\n{proposal}\n\n"
            "Perform the mandatory component-by-component audit in order, then render "
            "the overall_decision and list every imperfection with its responsible "
            "owner. Return only the JSON object with the exact required fields."
        )
        return run_structured_agent(
            "mentor", SYSTEM_PROMPT, user, self._model,
            semantic_validator=_semantic_validate,
        )