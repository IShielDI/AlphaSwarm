"""MCP-facing data client for agent data pulls.

Per TRD Section 2.3, every Layer-1 agent data pull (option chain, Greeks,
IV, historical bars) goes through this layer -- the functional equivalent
of the Alpaca Trading MCP Server tool surface for our build.

NOTE (Day 1): this exposes the exact option-chain / Greeks / IV / bars
queries the agents need, backed by the official `alpaca-py` data clients.
Standing up the separate external Node MCP server binary is deferred to
Day 2 wiring, when agents actually call this surface. No strategy, no LLM.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Sequence, Union

from alpaca.data.requests import OptionChainRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.enums import ContractType
from alpaca.trading.models import OptionContract

from .alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


class MCPDataClient:
    """Agent-facing option / IV / historical data pulls."""

    def __init__(self, alpaca_client: Optional[AlpacaClient] = None) -> None:
        self._client = alpaca_client or AlpacaClient()

    def get_option_chain(
        self,
        underlying: str,
        type_: Optional[ContractType] = None,
        expiration_date_lte: Optional[str] = None,
        expiration_date_gte: Optional[str] = None,
    ) -> dict:
        """Raw option chain for an underlying (keyed by contract symbol)."""
        return self._client.option_data.get_option_chain(
            OptionChainRequest(
                underlying_symbol=underlying,
                type=type_,
                expiration_date_lte=expiration_date_lte,
                expiration_date_gte=expiration_date_gte,
            )
        )

    def get_option_snapshot(self, symbols: Union[str, Sequence[str]]):
        """Raw per-symbol option snapshots (quote/trade, Greeks, IV)."""
        return self._client.get_option_snapshot(symbols)

    def get_option_greeks(self, symbol: str) -> Optional[dict]:
        """Parsed Greeks for a single option symbol."""
        item = self._snapshot_item(symbol)
        if item is None or item.greeks is None:
            return None
        g = item.greeks
        return dict(delta=g.delta, gamma=g.gamma, theta=g.theta, vega=g.vega, rho=g.rho)

    def get_implied_volatility(self, symbol: str) -> Optional[float]:
        """Current implied volatility (fraction, e.g. 0.18) for a symbol."""
        item = self._snapshot_item(symbol)
        return getattr(item, "implied_volatility", None) if item is not None else None

    def _snapshot_item(self, symbol: str):
        snap = self._client.get_option_snapshot(symbol)
        return snap.get(symbol) if hasattr(snap, "get") else None

    def get_iv_and_greeks_surface(
        self, underlying: str, expiration: str, near_strike: float, width: int = 4
    ) -> dict:
        """Compact IV + Greeks table around `near_strike` for one expiry.

        `expiration` is a YYMMDD string (e.g. "260903"). Contract metadata
        (strike/expiry) comes from the trading option-contracts endpoint;
        Greeks and implied vol come from option snapshots.
        """
        exp_date = _yymmdd_to_date(expiration)
        contracts: list[OptionContract] = self._client.get_option_contracts(
            underlying_symbols=[underlying],
            expiration_date=exp_date,
            strike_price_gte=near_strike - width,
            strike_price_lte=near_strike + width,
        )
        calls = [c for c in contracts if c.type == ContractType.CALL]
        calls.sort(key=lambda c: c.strike_price)
        rows = []
        if calls:
            symbols = [c.symbol for c in calls]
            snap = self._client.get_option_snapshot(symbols)
            for c in calls:
                item = snap.get(c.symbol) if hasattr(snap, "get") else None
                if item is None:
                    continue
                rows.append(
                    {
                        "symbol": c.symbol,
                        "strike": float(c.strike_price),
                        "underlying": c.underlying_symbol,
                        "expiration": _date_to_yymmdd(c.expiration_date),
                        "contract_type": c.type.value,
                        "iv": getattr(item, "implied_volatility", None),
                        "greeks": (
                            {
                                "delta": item.greeks.delta,
                                "gamma": item.greeks.gamma,
                                "theta": item.greeks.theta,
                                "vega": item.greeks.vega,
                            }
                            if item.greeks is not None else None
                        ),
                        "bid": (
                            item.latest_quote.bid_price
                            if item.latest_quote is not None else None
                        ),
                        "ask": (
                            item.latest_quote.ask_price
                            if item.latest_quote is not None else None
                        ),
                    }
                )
        return {"underlying": underlying, "expiration": expiration, "rows": rows}

    def get_stock_bars(
        self,
        symbols: Union[str, Sequence[str]],
        start: datetime,
        end: Optional[datetime] = None,
        timeframe: TimeFrame = TimeFrame.Day,
        limit: int = 500,
    ):
        return self._client.get_stock_bars(
            symbols, start=start, end=end, timeframe=timeframe, limit=limit
        )

    def get_option_spot(self, underlying: str) -> Optional[float]:
        return self._client.get_option_spot_price(underlying)
def _yymmdd_to_date(yymmdd: str):
    import datetime as _dt

    return _dt.date(2000 + int(yymmdd[0:2]), int(yymmdd[2:4]), int(yymmdd[4:6]))


def _date_to_yymmdd(d) -> str:
    return d.strftime("%y%m%d")


def parse_option_symbol(symbol: str):
    """Parse an Alpaca option symbol via regex.

    Format: <TICKER 1-4 chars><YYMMDD><C|P><strike*1000, 8 digits>
    e.g. SPY260903C00774000 or AAPL260918C00235000. Returns None on mismatch.
    """
    import re

    m = re.fullmatch(r"([A-Z]{1,4})(\d{6})([CP])(\d{8})", symbol)
    if not m:
        return None
    return {
        "underlying": m.group(1),
        "expiration": m.group(2),
        "kind": m.group(3),
        "strike": int(m.group(4)) / 1000.0,
    }
