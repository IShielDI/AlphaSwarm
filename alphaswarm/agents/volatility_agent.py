"""Volatility Agent (Agent Rules Section 1: owns IV / realized vol / term structure).

Model: DeepSeek via OpenRouter (locked). Output: exact VOLATILITY_SCHEMA.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from collections import defaultdict
from typing import Any, Dict, List, Optional

from ..data.mcp_client import MCPDataClient, parse_option_symbol
from .llm_client import MODEL_DEEPSEEK, run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Volatility Agent in a multi-agent trading system. You own \
volatility analysis ONLY: implied volatility level, realized vs implied comparison, and \
term structure. Do not comment on market trend, option contract selection, or portfolio \
context -- other agents own those domains.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) with \
EXACTLY these fields and no others:
{
  "volatility_regime": "<low | normal | elevated | high>",
  "iv_assessment": "<string: current IV level vs its own typical range, e.g. cheap/fair/expensive>",
  "realized_vol_assessment": "<string: realized vol level and recent behavior>",
  "term_structure_assessment": "<string: contango/backwardation and what it implies>",
  "confidence": <number 0.0-1.0>,
  "evidence": [<string citing specific numbers from the data>, ...],
  "warnings": [<string>, ...]
}"""


def realized_vol(closes: List[float], window: int = 20) -> Optional[float]:
    """Annualized realized vol from daily closes (std of log returns)."""
    if len(closes) < window + 1:
        return None
    rets = [math.log(closes[-i] / closes[-i - 1]) for i in range(1, window + 1)]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(252), 4)


def build_snapshot(mcp: MCPDataClient, ticker: str) -> Dict[str, Any]:
    """Deterministic vol snapshot: realized vol + ATM IV per expiry (no LLM)."""
    spot = mcp.get_option_spot(ticker)
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=140)
    bars_resp = mcp.get_stock_bars(ticker, start=start, end=end)
    bars = list(bars_resp[ticker]) if hasattr(bars_resp, "__getitem__") else []
    closes = [float(b.close) for b in bars]
    rv20 = realized_vol(closes, 20)
    rv10 = realized_vol(closes, 10)

    # ATM IV term structure: from the full chain, per expiry, take options
    # with strikes within ~1.5% of spot and average their IV.
    chain = mcp.get_option_chain(ticker)
    per_expiry: Dict[str, List[float]] = defaultdict(list)
    today = end.date()
    for sym, item in chain.items():
        info = parse_option_symbol(sym)
        if not info or item is None:
            continue
        strike = info["strike"]
        if spot and abs(strike / spot - 1) > 0.015:
            continue
        iv = getattr(item, "implied_volatility", None)
        if iv:
            per_expiry[info["expiration"]].append(float(iv))

    term = []
    for expiry, ivs in sorted(per_expiry.items()):
        try:
            exp = dt.date(2000 + int(expiry[:2]), int(expiry[2:4]), int(expiry[4:6]))
        except ValueError:
            continue
        dte = (exp - today).days
        if dte < 1:
            continue
        term.append(
            {
                "expiration": expiry,
                "dte": dte,
                "atm_iv": round(sum(ivs) / len(ivs), 4),
                "n_contracts": len(ivs),
            }
        )
    term = [t for t in term if t["dte"] <= 90][:8]

    return {
        "ticker": ticker,
        "spot": spot,
        "as_of": end.strftime("%Y-%m-%d"),
        "realized_vol_20d": rv20,
        "realized_vol_10d": rv10,
        "iv_term_structure": term,
        "note": "atm_iv is the mean Alpaca-reported implied volatility of contracts with strikes within 1.5% of spot (annualized fraction, e.g. 0.21 = 21%)",
    }


class VolatilityAgent:
    def __init__(self, mcp: MCPDataClient | None = None, model: str = MODEL_DEEPSEEK):
        self._mcp = mcp or MCPDataClient()
        self._model = model

    def analyze(self, ticker: str, past_context: str = "") -> Dict[str, Any]:
        snap = build_snapshot(self._mcp, ticker)
        user = (
            "Current volatility data snapshot for one underlying:\n"
            f"{snap}\n\n"
            "Assess the volatility regime, IV cheapness/expensiveness vs realized vol, "
            "and the term structure (contango vs backwardation). Cite specific numbers "
            "from the snapshot in the evidence strings. Return only the JSON object with "
            "the exact required fields."
        )
        if past_context:
            user += f"\n\n{past_context}"
        return run_structured_agent("volatility_agent", SYSTEM_PROMPT, user, self._model)