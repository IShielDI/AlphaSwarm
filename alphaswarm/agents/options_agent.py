"""Options Agent (Agent Rules Section 1: owns structures / Greeks / liquidity).

Model: Qwen3-Coder via OpenRouter (locked -- most rigid schema of the four).
Output: exact OPTIONS_SCHEMA.

Hard scope rule (Agent Rules Section 3.7): vertical credit spreads ONLY
(bull put / bear call). Naked options, condors, straddles/strangles are out
of scope and rejected by the semantic validator, not left to the model.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Any, Dict, List

from .. import config
from ..data.mcp_client import MCPDataClient
from .llm_client import MODEL_QWEN3_CODER, run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Options Agent in a multi-agent trading system. You own option \
structure analysis ONLY: candidate vertical credit spreads, their contracts, Greeks, and \
liquidity. Do not assess market trend, volatility regime, or portfolio impact -- other \
agents own those domains.

HARD SCOPE: vertical credit spreads only -- bull_put_spread or bear_call_spread. Never \
propose naked options, iron condors, straddles, or strangles.

Use the ACTUAL bid/ask/IV/Greeks from the provided surface for your numbers -- do not \
invent quotes. Strikes must come from the surface.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) with \
EXACTLY these fields and no others:
{
  "candidate_structures": ["bull_put_spread" and/or "bear_call_spread"],
  "contract_candidates": [
    {
      "structure": "bull_put_spread",
      "short_leg": {"symbol": "<Alpaca OCC symbol from surface>", "strike": <number>},
      "long_leg": {"symbol": "<Alpaca OCC symbol from surface>", "strike": <number>},
      "estimated_credit": <net credit per share from actual bid/ask>,
      "max_loss_per_contract": <(width - credit) * 100>,
      "dte": <days to expiration>
    }
  ],
  "structure_rationale": "<why these structures fit a credit-spread approach>",
  "greeks": {"<structure or symbol>": {"delta": <n>, "gamma": <n>, "theta": <n>, "vega": <n>}, ...},
  "liquidity_assessment": "<string: bid/ask widths, whether fills are realistic>",
  "payoff_profile": "<string: max profit, max loss, breakeven(s)>",
  "risks": [<string>, ...],
  "confidence": <number 0.0-1.0>
}"""


def _pick_expiration(contracts: List, today: dt.date):
    """Nearest expiration with MIN_DTE <= DTE <= MAX_DTE (config swing horizon)."""
    exps = sorted({c.expiration_date for c in contracts})
    for e in exps:
        if config.MIN_DTE <= (e - today).days <= config.MAX_DTE:
            return e
    return None


def build_surface(mcp: MCPDataClient, ticker: str) -> Dict[str, Any]:
    """Deterministic puts+calls IV/Greeks/quote surface around spot (no LLM)."""
    spot = mcp.get_option_spot(ticker)
    today = dt.datetime.now(dt.timezone.utc).date()
    gte = today + dt.timedelta(days=config.MIN_DTE)
    lte = today + dt.timedelta(days=config.MAX_DTE + 7)
    contracts = mcp._client.get_option_contracts(
        [ticker], expiration_date_gte=gte, expiration_date_lte=lte
    )
    expiry = _pick_expiration(contracts, today)
    if expiry is None or spot is None:
        raise RuntimeError(
            f"no suitable expiration ({config.MIN_DTE}-{config.MAX_DTE} DTE) for {ticker}"
        )

    lo, hi = spot * 0.92, spot * 1.08
    picked = [
        c for c in contracts
        if c.expiration_date == expiry and lo <= float(c.strike_price) <= hi
    ]
    symbols = [c.symbol for c in picked]
    snap = {}
    for i in range(0, len(symbols), 100):  # Alpaca limit: 100 symbols/request
        chunk = symbols[i : i + 100]
        snap.update(mcp._client.get_option_snapshot(chunk) or {})
    rows = []
    for c in picked:
        item = snap.get(c.symbol) if hasattr(snap, "get") else None
        if item is None:
            continue
        quote = item.latest_quote
        g = item.greeks
        rows.append(
            {
                "symbol": c.symbol,
                "type": c.type.value,
                "strike": float(c.strike_price),
                "iv": round(float(getattr(item, "implied_volatility", 0) or 0), 4),
                "delta": g.delta if g else None,
                "gamma": g.gamma if g else None,
                "theta": g.theta if g else None,
                "vega": g.vega if g else None,
                "bid": float(quote.bid_price) if quote else None,
                "ask": float(quote.ask_price) if quote else None,
            }
        )
    return {
        "ticker": ticker,
        "spot": spot,
        "expiration": expiry.strftime("%y%m%d"),
        "dte": (expiry - today).days,
        "surface": rows,
        "note": "bid/ask per share; strikes within 8% of spot; use ONLY these symbols/strikes",
    }


def _semantic_validate(out: Dict[str, Any]) -> List[str]:
    """Beyond-schema checks: spread-type scope, leg consistency."""
    errors: List[str] = []
    structures = out.get("candidate_structures")
    if not isinstance(structures, list) or not structures:
        return ["candidate_structures must be a non-empty list"]
    for s in structures:
        if s not in config.ALLOWED_STRUCTURES:
            errors.append(f"disallowed structure {s!r} (vertical credit spreads only)")

    cands = out.get("contract_candidates")
    if not isinstance(cands, list) or not cands:
        errors.append("contract_candidates must be a non-empty list")
        return errors
    for i, cand in enumerate(cands):
        if not isinstance(cand, dict):
            errors.append(f"contract_candidates[{i}] must be an object")
            continue
        struct = cand.get("structure")
        if struct not in config.ALLOWED_STRUCTURES:
            errors.append(f"contract_candidates[{i}].structure {struct!r} not allowed")
        short_leg, long_leg = cand.get("short_leg"), cand.get("long_leg")
        for name, leg in (("short_leg", short_leg), ("long_leg", long_leg)):
            if not isinstance(leg, dict) or "symbol" not in leg or "strike" not in leg:
                errors.append(f"contract_candidates[{i}].{name} needs symbol+strike")
        if isinstance(short_leg, dict) and isinstance(long_leg, dict):
            ss, ls = short_leg.get("strike"), long_leg.get("strike")
            if struct == "bull_put_spread" and ss is not None and ls is not None and not ss > ls:
                errors.append(
                    f"contract_candidates[{i}]: bull put needs short strike > long strike"
                )
            if struct == "bear_call_spread" and ss is not None and ls is not None and not ss < ls:
                errors.append(
                    f"contract_candidates[{i}]: bear call needs short strike < long strike"
                )
    return errors


class OptionsAgent:
    def __init__(self, mcp: MCPDataClient | None = None, model: str = MODEL_QWEN3_CODER):
        self._mcp = mcp or MCPDataClient()
        self._model = model

    def analyze(self, ticker: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        surface = build_surface(self._mcp, ticker)
        ctx = context or {}
        user = (
            f"Option surface for {ticker}:\n{surface}\n\n"
            f"Context from other agents (for direction fit only, not your domain): {ctx}\n\n"
            "Propose 1-2 vertical credit spread candidates consistent with the directional "
            "context, using only strikes/symbols from the surface with real bid/ask numbers. "
            "Return only the JSON object with the exact required fields."
        )
        return run_structured_agent(
            "options_agent", SYSTEM_PROMPT, user, self._model,
            semantic_validator=_semantic_validate,
        )