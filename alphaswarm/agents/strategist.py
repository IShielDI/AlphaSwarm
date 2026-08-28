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
    ) -> Any:
        """Return a proposal dict or the literal string "NO_TRADE"."""
        user = (
            f"Underlying: {ticker}\n\n"
            f"MARKET AGENT output:\n{market_analysis}\n\n"
            f"VOLATILITY AGENT output:\n{volatility_analysis}\n\n"
            f"OPTIONS AGENT output:\n{options_analysis}\n\n"
            f"PORTFOLIO AGENT output:\n{portfolio_analysis}\n\n"
            "Synthesize these four outputs into exactly one decision. If they disagree, "
            "if evidence is weak, or if risk is poor, output the literal JSON string "
            "\"NO_TRADE\" instead of a proposal. Otherwise return only the JSON proposal "
            "object with the exact required fields."
        )
        return run_structured_agent(
            "strategist", SYSTEM_PROMPT, user, self._model,
            provider="google", semantic_validator=_semantic_validate,
        )