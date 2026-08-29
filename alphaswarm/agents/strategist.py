"""Strategist (Agent Rules Section 1: owns synthesis into ONE trade proposal).

Model: Gemini Flash via Google AI Studio (locked). Output: exact
STRATEGIST_SCHEMA, or the literal "NO_TRADE" (Agent Rules Section 3.2 --
NO TRADE is a valid, expected outcome, never forced).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .. import config
from .llm_client import MODEL_GEMINI_FLASH, run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Strategist in a multi-agent trading system. You own \
synthesis ONLY: combining the four Layer-1 agent outputs into exactly one trade proposal. \
Do not re-do their analysis or invent data they did not provide.

HARD RULES:
- You MUST explicitly consider at least one alternative structure (1-2) in \
"alternative_structures_considered" before selecting.
- NO_TRADE is a valid and expected final answer, not an edge case. If the signals \
disagree (e.g. market bias conflicts with volatility assessment), if evidence is weak, \
if liquidity or portfolio context is poor, or confidence is low -- output NO_TRADE. \
Never force a trade just because the pipeline ran.
- IV INTERPRETATION (critical, do not get this backwards): you synthesize SELLERS of \
premium (vertical credit spreads). IV EXPENSIVE relative to realized vol is FAVORABLE -- \
you collect richer credit for the same risk. IV CHEAP relative to realized is a reason \
FOR CAUTION (thin premium), not a selling opportunity. "Expensive IV" alone must never \
appear in reasons_not_to_trade; only flag IV when it contradicts the direction (e.g. \
short-dated event spikes against the bias) or the Volatility Agent itself warns against \
selling.

Respond with a single JSON value and NOTHING else (no prose, no markdown fences). \
Either the literal JSON string "NO_TRADE", or a JSON object with EXACTLY these fields \
and no others:
{
  "underlying": "<ticker>",
  "market_thesis": "<one paragraph synthesizing the Market Agent>",
  "volatility_thesis": "<one paragraph synthesizing the Volatility Agent>",
  "selected_structure": "<bull_put_spread | bear_call_spread>",
  "contract": {"short_leg": {"symbol": "<OCC symbol>", "strike": <n>}, "long_leg": {"symbol": "<OCC symbol>", "strike": <n>}, "expiration": "<YYMMDD>", "estimated_credit": <n>, "max_loss_per_contract": <n>},
  "rationale": "<why this proposal, referencing the agents' outputs>",
  "alternative_structures_considered": [<string, string>],
  "entry_conditions": [<string>, ...],
  "exit_conditions": [<string>, ...],
  "invalidation_conditions": [<string>, ...],
  "portfolio_impact": "<synthesizing the Portfolio Agent>",
  "max_loss": <number in dollars for the proposed contract count>,
  "key_risks": [<string>, ...],
  "confidence": <number 0.0-1.0>,
  "reasons_not_to_trade": [<string, MUST be non-empty: honest counter-arguments>]
}"""


def _semantic_validate(out: Any) -> list:
    if not isinstance(out, dict):
        return []  # the literal NO_TRADE string is validated by the schema layer
    errors = []
    if out.get("selected_structure") not in config.ALLOWED_STRUCTURES:
        errors.append(
            f"selected_structure must be one of {config.ALLOWED_STRUCTURES}"
        )
    alts = out.get("alternative_structures_considered")
    if not isinstance(alts, list) or len(alts) < 1:
        errors.append("alternative_structures_considered must list at least 1 alternative")
    rnt = out.get("reasons_not_to_trade")
    if not isinstance(rnt, list) or len(rnt) < 1:
        errors.append("reasons_not_to_trade must be a non-empty list")
    contract = out.get("contract")
    if not isinstance(contract, dict):
        errors.append("contract must be an object")
    return errors


class Strategist:
    def __init__(self, model: str = MODEL_GEMINI_FLASH):
        self._model = model

    def synthesize(
        self,
        ticker: str,
        market_analysis: Dict[str, Any],
        volatility_analysis: Dict[str, Any],
        options_analysis: Dict[str, Any],
        portfolio_analysis: Dict[str, Any],
        mentor_feedback: Dict[str, Any] | None = None,
        past_context: str = "",
    ) -> Any:
        """Return a proposal dict or the literal string "NO_TRADE".

        `mentor_feedback` (optional) carries the Mentor's audit during the
        single correction round (Agent Rules 3.3); the Strategist must
        address each imperfection or return NO_TRADE.

        `past_context` (optional) is a pre-formatted block of similar past
        decisions from the retrieval system.
        """
        user = (
            f"Underlying: {ticker}\n\n"
            f"MARKET AGENT output:\n{market_analysis}\n\n"
            f"VOLATILITY AGENT output:\n{volatility_analysis}\n\n"
            f"OPTIONS AGENT output:\n{options_analysis}\n\n"
            f"PORTFOLIO AGENT output:\n{portfolio_analysis}\n\n"
            + (
                (
                    "MENTOR AUDIT of your previous proposal (correction round -- address "
                    f"every imperfection or return NO_TRADE):\n{mentor_feedback}\n\n"
                )
                if mentor_feedback
                else ""
            )
            + (f"{past_context}\n\n" if past_context else "")
            + "Synthesize these four outputs into exactly one decision. If they disagree, "
            "if evidence is weak, or if risk is poor, output the literal JSON string "
            "\"NO_TRADE\" instead of a proposal. Otherwise return only the JSON proposal "
            "object with the exact required fields."
        )
        return run_structured_agent(
            "strategist", SYSTEM_PROMPT, user, self._model,
            provider="google", semantic_validator=_semantic_validate,
        )


CONSERVATIVE_SYSTEM_PROMPT = """You are the Conservative Strategist in a multi-agent trading system. You own \
synthesis ONLY: combining the four Layer-1 agent outputs into at most ONE trade proposal. \
Do not re-do their analysis or invent data they did not provide.

CONSERVATIVE RULES & HIGH CONFIDENCE THRESHOLD:
- You operate under a strict conservative bias ("skip unless very high confidence").
- NO_TRADE is your DEFAULT stance whenever there is any signal disagreement, moderate confidence (<0.8), \
or potential portfolio conflict.
- You MUST explicitly consider at least one alternative structure (1-2) in "alternative_structures_considered" before selecting.

Respond with a single JSON value and NOTHING else (no prose, no markdown fences). \
Either the literal JSON string "NO_TRADE", or a JSON object with EXACTLY these fields \
and no others:
{
  "underlying": "<ticker>",
  "market_thesis": "<one paragraph synthesizing the Market Agent>",
  "volatility_thesis": "<one paragraph synthesizing the Volatility Agent>",
  "selected_structure": "<bull_put_spread | bear_call_spread>",
  "contract": {"short_leg": {"symbol": "<OCC symbol>", "strike": <n>}, "long_leg": {"symbol": "<OCC symbol>", "strike": <n>}, "expiration": "<YYMMDD>", "estimated_credit": <n>, "max_loss_per_contract": <n>},
  "rationale": "<why this proposal, referencing the agents' outputs>",
  "alternative_structures_considered": [<string, string>],
  "entry_conditions": [<string>, ...],
  "exit_conditions": [<string>, ...],
  "invalidation_conditions": [<string>, ...],
  "portfolio_impact": "<synthesizing the Portfolio Agent>",
  "max_loss": <number in dollars for the proposed contract count>,
  "key_risks": [<string>, ...],
  "confidence": <number 0.0-1.0>,
  "reasons_not_to_trade": [<string, MUST be non-empty: honest counter-arguments>]
}"""


class ConservativeStrategist(Strategist):
    """Alternative Strategist variant biased toward conservative high-confidence filtering."""

    def synthesize(
        self,
        ticker: str,
        market_analysis: Dict[str, Any],
        volatility_analysis: Dict[str, Any],
        options_analysis: Dict[str, Any],
        portfolio_analysis: Dict[str, Any],
        mentor_feedback: Dict[str, Any] | None = None,
        past_context: str = "",
    ) -> Any:
        user = (
            f"Underlying: {ticker}\n\n"
            f"MARKET AGENT output:\n{market_analysis}\n\n"
            f"VOLATILITY AGENT output:\n{volatility_analysis}\n\n"
            f"OPTIONS AGENT output:\n{options_analysis}\n\n"
            f"PORTFOLIO AGENT output:\n{portfolio_analysis}\n\n"
            + (
                (
                    "MENTOR AUDIT of your previous proposal (correction round -- address "
                    f"every imperfection or return NO_TRADE):\n{mentor_feedback}\n\n"
                )
                if mentor_feedback
                else ""
            )
            + (f"{past_context}\n\n" if past_context else "")
            + "Synthesize these four outputs into at most one decision under your conservative "
            "rules. Unless confidence is high and evidence is compelling across all inputs, "
            "output the literal JSON string \"NO_TRADE\". Otherwise return only the JSON "
            "proposal object with the exact required fields."
        )
        return run_structured_agent(
            "conservative_strategist", CONSERVATIVE_SYSTEM_PROMPT, user, self._model,
            provider="google", semantic_validator=_semantic_validate,
        )


def arbitrate_proposals(primary: Any, secondary: Any) -> tuple[Any, Dict[str, Any]]:
    """Arbitrate between Primary and Secondary (Conservative) Strategist outputs.

    Rules:
    - Both agree on NO_TRADE -> returns ("NO_TRADE", metadata)
    - Both agree on same structure -> returns (primary_proposal, metadata)
    - Disagree (one NO_TRADE, or different structures) -> surfaces both proposals
      in a single proposal object for the Mentor to audit and choose/reject both,
      without modifying the Mentor audit code.
    """
    p1_is_notrade = primary == "NO_TRADE" or not isinstance(primary, dict)
    p2_is_notrade = secondary == "NO_TRADE" or not isinstance(secondary, dict)

    if p1_is_notrade and p2_is_notrade:
        return "NO_TRADE", {
            "agreed": True,
            "decision": "NO_TRADE",
            "reason": "Both strategists agreed on NO_TRADE",
        }

    if not p1_is_notrade and not p2_is_notrade:
        s1 = primary.get("selected_structure")
        s2 = secondary.get("selected_structure")
        if s1 == s2:
            return primary, {
                "agreed": True,
                "decision": "PROCEED",
                "structure": s1,
                "reason": f"Both strategists agreed on structure {s1}",
            }

    # Disagreement handling: surface both to Mentor via the proposal dictionary.
    if not p1_is_notrade and p2_is_notrade:
        surfaced = dict(primary)
        surfaced["dual_strategist_arbitration"] = {
            "disagreement": True,
            "primary_proposal": primary,
            "secondary_proposal": "NO_TRADE",
            "note": "Primary Strategist proposed a trade, but Secondary (Conservative) Strategist recommended NO_TRADE.",
        }
        return surfaced, {
            "agreed": False,
            "decision": "DISAGREEMENT_SURFACED_TO_MENTOR",
            "reason": "Primary proposed trade; Secondary recommended NO_TRADE",
        }

    if p1_is_notrade and not p2_is_notrade:
        surfaced = dict(secondary)
        surfaced["dual_strategist_arbitration"] = {
            "disagreement": True,
            "primary_proposal": "NO_TRADE",
            "secondary_proposal": secondary,
            "note": "Primary Strategist recommended NO_TRADE, but Secondary (Conservative) Strategist proposed a trade.",
        }
        return surfaced, {
            "agreed": False,
            "decision": "DISAGREEMENT_SURFACED_TO_MENTOR",
            "reason": "Primary recommended NO_TRADE; Secondary proposed trade",
        }

    # Both proposed trades, but different structures
    surfaced = dict(primary)
    surfaced["dual_strategist_arbitration"] = {
        "disagreement": True,
        "primary_proposal": primary,
        "secondary_proposal": secondary,
        "note": f"Primary Strategist proposed '{primary.get('selected_structure')}', but Secondary Strategist proposed '{secondary.get('selected_structure')}'.",
    }
    return surfaced, {
        "agreed": False,
        "decision": "DISAGREEMENT_SURFACED_TO_MENTOR",
        "reason": f"Primary proposed {primary.get('selected_structure')}; Secondary proposed {secondary.get('selected_structure')}",
    }