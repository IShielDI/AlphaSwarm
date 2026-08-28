"""Portfolio Agent (Agent Rules Section 1: owns exposure / concentration / conflicts).

Model: GLM-4.5-Air via OpenRouter (locked). Output: exact PORTFOLIO_SCHEMA.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from ..data.alpaca_client import AlpacaClient
from ..data.mcp_client import parse_option_symbol
from .llm_client import MODEL_GLM45_AIR, run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Portfolio Agent in a multi-agent trading system. You own \
portfolio context ONLY: current exposure, how a new position would fit, concentration risk, \
correlation risk, and conflicts with existing positions. Do not assess market direction, \
volatility, or option structures -- other agents own those domains.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) with \
EXACTLY these fields and no others:
{
  "current_exposure": "<string: summary of account equity and open positions relevant to the underlying>",
  "portfolio_impact": "<string: what adding this spread would do to exposure/risk budget>",
  "concentration_risk": "<string: whether the new position would over-concentrate the account>",
  "correlation_risk": "<string: correlation of the proposed underlying with existing holdings>",
  "conflicts": [<string: any offsetting/duplicating existing positions, or empty>],
  "recommendation": "<proceed | proceed_with_caution | do_not_proceed>"
}"""


def build_snapshot(ticker: str, alpaca: AlpacaClient | None = None) -> Dict[str, Any]:
    """Deterministic account/positions snapshot (no LLM)."""
    client = alpaca or AlpacaClient()
    summary = client.get_account_summary()
    positions = client.get_positions()
    pos_rows = []
    for p in positions:
        row = {
            "symbol": p.symbol,
            "qty": float(p.qty),
            "side": p.side,
            "market_value": float(p.market_value),
        }
        info = parse_option_symbol(p.symbol)
        if info:
            row = {
                "symbol": p.symbol,
                "underlying": info["underlying"],
                "type": "option_" + ("put" if info["kind"] == "P" else "call"),
                "strike": info["strike"],
                "expiration": info["expiration"],
                "qty": float(p.qty),
                "side": p.side,
                "market_value": float(p.market_value),
            }
        pos_rows.append(row)
    exposure_by_underlying: Dict[str, float] = {}
    for row in pos_rows:
        u = row.get("underlying", row["symbol"])
        exposure_by_underlying[u] = round(
            exposure_by_underlying.get(u, 0.0) + abs(row["market_value"]), 2
        )
    return {
        "account": summary,
        "positions": pos_rows,
        "abs_market_value_by_underlying": exposure_by_underlying,
        "proposed_underlying": ticker,
        "note": "market_value is negative for short premium (credit) option positions",
    }


class PortfolioAgent:
    def __init__(self, alpaca: AlpacaClient | None = None, model: str = MODEL_GLM45_AIR):
        self._alpaca = alpaca
        self._model = model

    def analyze(self, ticker: str, context: Dict[str, Any] | None = None) -> Dict[str, Any]:
        snap = build_snapshot(ticker, self._alpaca)
        ctx = context or {}
        user = (
            "Current account/portfolio snapshot:\n"
            f"{snap}\n\n"
            f"Context from other agents (not your domain): {ctx}\n\n"
            "Assess how a new vertical credit spread on the proposed underlying would fit "
            "the current portfolio: exposure, concentration, correlation, conflicts. "
            "Return only the JSON object with the exact required fields."
        )
        return run_structured_agent("portfolio_agent", SYSTEM_PROMPT, user, self._model)