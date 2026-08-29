"""Market Agent (Agent Rules Section 1: owns trend / regime / directional bias).

Model: DeepSeek via OpenRouter (locked). Output: exact MARKET_SCHEMA.
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Any, Dict

from ..data.mcp_client import MCPDataClient
from .llm_client import MODEL_DEEPSEEK, run_structured_agent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the Market Agent in a multi-agent trading system. You own market \
analysis ONLY: trend, market regime, and directional bias. Do not comment on volatility, \
options, portfolio context, or trade selection -- other agents own those domains.

Respond with a single JSON object and NOTHING else (no prose, no markdown fences) with \
EXACTLY these fields and no others:
{
  "market_regime": "<trending_up | trending_down | range_bound | choppy>",
  "directional_bias": "<bullish | bearish | neutral>",
  "confidence": <number 0.0-1.0>,
  "supporting_evidence": [<string>, ...],
  "contradictory_evidence": [<string>, ...],
  "risk_factors": [<string>, ...]
}"""


def build_snapshot(mcp: MCPDataClient, ticker: str) -> Dict[str, Any]:
    """Deterministic price/trend snapshot from daily bars (no LLM)."""
    spot = mcp.get_option_spot(ticker)
    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=140)
    bars_resp = mcp.get_stock_bars(ticker, start=start, end=end)
    bars = list(bars_resp[ticker]) if hasattr(bars_resp, "__getitem__") else []
    closes = [float(b.close) for b in bars]
    volumes = [float(b.volume) for b in bars]

    def sma(n: int):
        return round(sum(closes[-n:]) / n, 2) if len(closes) >= n else None

    def ret(n: int):
        if len(closes) > n and closes[-n - 1] != 0:
            return round(closes[-1] / closes[-n - 1] - 1, 4)
        return None

    def logret(n: int):
        if len(closes) > n and closes[-n - 1] > 0 and closes[-1] > 0:
            return round(math.log(closes[-1] / closes[-n - 1]), 4)
        return None

    recent = closes[-60:] if len(closes) >= 60 else closes
    return {
        "ticker": ticker,
        "spot": spot,
        "as_of": end.strftime("%Y-%m-%d"),
        "sma_20": sma(20),
        "sma_50": sma(50),
        "return_5d_pct": ret(5),
        "return_20d_pct": ret(20),
        "log_return_20d": logret(20),
        "high_60d": max(recent) if recent else None,
        "low_60d": min(recent) if recent else None,
        "volume_ratio_5d_vs_60d": (
            round(sum(volumes[-5:]) / 5 / (sum(volumes[-60:]) / 60), 2)
            if len(volumes) >= 60 and sum(volumes[-60:]) > 0
            else None
        ),
        "last_10_closes": closes[-10:],
    }


class MarketAgent:
    def __init__(self, mcp: MCPDataClient | None = None, model: str = MODEL_DEEPSEEK):
        self._mcp = mcp or MCPDataClient()
        self._model = model

    def analyze(self, ticker: str, past_context: str = "") -> Dict[str, Any]:
        snap = build_snapshot(self._mcp, ticker)
        user = (
            "Current market data snapshot for one underlying:\n"
            f"{snap}\n\n"
            "Classify the market regime and directional bias. Base every claim on the "
            "numbers above (name them explicitly in the evidence strings). Return only "
            "the JSON object with the exact required fields."
        )
        if past_context:
            user += f"\n\n{past_context}"
        return run_structured_agent("market_agent", SYSTEM_PROMPT, user, self._model)