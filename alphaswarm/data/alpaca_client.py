"""Direct alpaca-py wrapper.

Used by the deterministic, no-LLM portions of the system (Risk Engine,
Execution Service, backtest) and by the agent-facing data pulls.

Two distinct surfaces:
  * TradingClient        -- account state, positions, option contracts, order submission
  * Option/Stock historical data clients -- option chain, Greeks/IV snapshots, bars

Everything here is a thin, typed wrapper; it holds no "strategy" logic.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import List, Optional, Sequence, Union

from alpaca.data.enums import DataFeed
from alpaca.data.historical import (
    OptionHistoricalDataClient,
    StockHistoricalDataClient,
)
from alpaca.data.requests import (
    OptionChainRequest,
    OptionSnapshotRequest,
    StockBarsRequest,
    StockSnapshotRequest,
)
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetOptionContractsRequest
from alpaca.trading.models import OptionContract

from .. import config

logger = logging.getLogger(__name__)


class AlpacaClient:
    """Convenience wrapper around alpaca-py for paper trading + market data."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        paper: bool = True,
    ) -> None:
        self._api_key = api_key or config.ALPACA_API_KEY
        self._secret_key = secret_key or config.ALPACA_SECRET_KEY
        if not self._api_key or not self._secret_key or not self._api_key.startswith("PK"):
            raise RuntimeError("Alpaca creds missing: set ALPACA_API_KEY/SECRET_KEY.")

        self.trading = TradingClient(
            self._api_key, self._secret_key, paper=paper
        )
        self.option_data = OptionHistoricalDataClient(
            self._api_key, self._secret_key
        )
        self.stock_data = StockHistoricalDataClient(
            self._api_key, self._secret_key
        )
# ------------------------------------------------------------------
    # Account / positions
    # ------------------------------------------------------------------
    def get_account(self):
        """Raw account object (buying power, equity, etc.)."""
        return self.trading.get_account()

    def get_positions(self):
        """All open positions (raw)."""
        return self.trading.get_all_positions()

    def get_account_summary(self) -> dict:
        """Compact account summary (equity, buying power, cash)."""
        acc = self.get_account()
        return {
            "equity": float(acc.equity),
            "buying_power": float(acc.buying_power),
            "cash": float(acc.cash),
            "daytrading_buying_power": (
                float(acc.daytrading_buying_power)
                if acc.daytrading_buying_power else None
            ),
        }

    # ------------------------------------------------------------------
    # Option contracts (chain) -- TradingClient
    # ------------------------------------------------------------------
    def get_option_contracts(
        self,
        underlying_symbols: Sequence[str],
        expiration_date: Optional[Union[date, str]] = None,
        expiration_date_lte: Optional[Union[date, str]] = None,
        expiration_date_gte: Optional[Union[date, str]] = None,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        limit: int = 1000,
    ) -> List[OptionContract]:
        """Return a list of option contracts for the given underlyings."""
        req = GetOptionContractsRequest(
            underlying_symbols=list(underlying_symbols),
            expiration_date=expiration_date,
            expiration_date_gte=expiration_date_gte,
            expiration_date_lte=expiration_date_lte,
            strike_price_gte=(
                str(strike_price_gte) if strike_price_gte is not None else None
            ),
            strike_price_lte=(
                str(strike_price_lte) if strike_price_lte is not None else None
            ),
            limit=limit,
        )
        resp = self.trading.get_option_contracts(req)
        return list(resp.option_contracts)

    # ------------------------------------------------------------------
    # Option chain / Greeks / IV (option data client)
    # ------------------------------------------------------------------
    def get_option_chain(self, underlying_symbol: str):
        """Return the option chain for `underlying_symbol` (raw response dict)."""
        req = OptionChainRequest(underlying_symbol=underlying_symbol)
        return self.option_data.get_option_chain(req)

    def get_option_snapshot(self, symbols: Union[str, Sequence[str]]):
        """Per-symbol option snapshots (includes Greeks + implied vol)."""
        req = OptionSnapshotRequest(symbol_or_symbols=symbols)
        return self.option_data.get_option_snapshot(req)

    # ------------------------------------------------------------------
    # Stock bars / snapshots -- underlying prices + current quote
    # ------------------------------------------------------------------
    def get_stock_bars(
        self,
        symbols: Union[str, Sequence[str]],
        start: datetime,
        end: Optional[datetime] = None,
        timeframe: TimeFrame = TimeFrame.Day,
        limit: int = 500,
    ):
        req = StockBarsRequest(
            symbol_or_symbols=symbols,
            start=start,
            end=end,
            timeframe=timeframe,
            limit=limit,
            feed=DataFeed.IEX,
        )
        return self.stock_data.get_stock_bars(req)

    def get_stock_snapshot(self, symbols):
        req = StockSnapshotRequest(symbol_or_symbols=symbols)
        return self.stock_data.get_stock_snapshot(req)

    def get_option_spot_price(self, underlying: str) -> Optional[float]:
        """Latest underlying price via stock snapshot (for spread selection)."""
        snap = self.stock_data.get_stock_snapshot(
            StockSnapshotRequest(symbol_or_symbols=underlying)
        )
        item = snap.get(underlying) if hasattr(snap, "get") else None
        if item is None:
            return None
        quote = item.latest_quote
        if quote is not None and quote.ask_price is not None:
            return float(quote.ask_price)
        trade = item.latest_trade
        return float(trade.price) if trade is not None else None

    def close(self):
        """No persistent connections in alpaca-py; kept for interface parity."""
        return None
