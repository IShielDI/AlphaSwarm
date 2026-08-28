"""Day 1 deterministic backtest of the entry rule (NO LLM).

Rule under test (PRD Section 4): directional bias + elevated vol rank -> sell
a vertical credit spread.

HONEST DATA CAVEATS (stated up front, not buried):
  * Historical IMPLIED volatility is NOT available on the free Alpaca feed
    (option snapshots are current-only). We use trailing 20-day REALIZED
    volatility as the IV-rank proxy and estimate the spread credit with a
    Black-Scholes model driven by that realized vol. Explicit approximation.
  * The simulated horizon outcome is mark-to-model: above the short strike we
    take the full credit; below the long strike we take max loss; between we
    interpolate linearly. It is NOT actual filled option PnL.
  * Sample is ~1 calendar year per ticker (small for a vol strategy). Any
    conclusion is provisional; the PRD explicitly does not claim significance.

Pure deterministic Python (numpy/pandas only, no LLM).
"""

from __future__ import annotations

import datetime as dt
import logging
import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .. import config
from ..data.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)

RF = 0.0
LOOKBACK = 1800   # calendar days of daily bars to pull (~6 yrs IEX history)
SMA_WINDOW = 50
VOL_WINDOW = 20
VOL_RANK_LOOKBACK = 252
VOL_RANK_QUANTILE = 0.70
SPREAD_WIDTH = 5.0
OTM_PCT = 0.05
HORIZON = 10


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_put_premium(s, k, t, vol, r=RF):
    if vol <= 0 or t <= 0:
        return max(k - s, 0.0)
    d1 = (math.log(s / k) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return k * math.exp(-r * t) * _normal_cdf(-d2) - s * _normal_cdf(-d1)


def bs_call_premium(s, k, t, vol, r=RF):
    if vol <= 0 or t <= 0:
        return max(s - k, 0.0)
    d1 = (math.log(s / k) + (r + 0.5 * vol * vol) * t) / (vol * math.sqrt(t))
    d2 = d1 - vol * math.sqrt(t)
    return s * _normal_cdf(d1) - k * math.exp(-r * t) * _normal_cdf(d2)


def annualized_realized_vol(closes: pd.Series, window: int = VOL_WINDOW) -> pd.Series:
    log_ret = np.log(closes / closes.shift(1))
    return log_ret.rolling(window).std(ddof=1) * math.sqrt(252)
class BacktestResult:
    def __init__(self) -> None:
        self.trades: List[dict] = []
        self.metrics: Dict = {}

    def add(self, **kwargs) -> None:
        self.trades.append(kwargs)

    def summarize(self) -> dict:
        df = pd.DataFrame(self.trades)
        if df.empty:
            self.metrics = {"n_trades": 0, "note": "no qualifying setups"}
            return self.metrics
        wins = int((df["pnl_per_spread"] > 0).sum())
        n = len(df)
        m = {
            "n_trades": n,
            "win_rate": wins / n,
            "avg_pnl_per_spread_dollars": float(df["pnl_per_spread"].mean()),
            "total_pnl_per_1_contract_dollars": float(df["pnl_per_spread"].sum()),
            "mean_credit_received": float(df["credit"].mean()),
            "max_single_loss": float(df["pnl_per_spread"].min()),
            "by_ticker": df.groupby("ticker")["pnl_per_spread"]
                            .agg(["count", "mean", "sum"]).to_dict("index"),
        }
        self.metrics = m
        return m
class HistoricalBacktest:
    def __init__(self, client: Optional[AlpacaClient] = None,
                 tickers: Optional[List[str]] = None) -> None:
        self._client = client or AlpacaClient()
        self.tickers = tickers or config.TICKER_UNIVERSE

    def _load_closes(self, ticker: str) -> pd.Series:
        end = dt.datetime.now(dt.timezone.utc)
        start = end - dt.timedelta(days=LOOKBACK)
        bars = self._client.get_stock_bars(
            ticker, start=start, end=end, limit=LOOKBACK
        )
        df = bars.df
        if ticker in df.index.get_level_values(0):
            df = df.xs(ticker)
        df = df.sort_index()
        df["close"] = df["close"].astype(float)
        df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
        return df["close"]

    def run(self) -> BacktestResult:
        res = BacktestResult()
        for ticker in self.tickers:
            try:
                closes = self._load_closes(ticker)
            except Exception as e:  # noqa: BLE001 - keep one bad ticker from killing run
                logger.warning("skip %s: %s", ticker, e)
                continue
            if len(closes) < (SMA_WINDOW + VOL_RANK_LOOKBACK + HORIZON + 20):
                logger.warning("skip %s: insufficient history (%d bars)", ticker, len(closes))
                continue
            self._run_ticker(ticker, closes, res)
        res.summarize()
        return res

    def _run_ticker(self, ticker: str, closes: pd.Series, res: BacktestResult) -> None:
        sma = closes.rolling(SMA_WINDOW).mean()
        rv = annualized_realized_vol(closes)
        # Daily realized-vol rank vs its trailing ~1yr distribution (IV-rank proxy).
        vol_rank = rv.rolling(VOL_RANK_LOOKBACK, min_periods=1).apply(
            lambda x: float((x.iloc[-1] >= x).mean()), raw=False
        )
        dates = closes.index
        for i in range(VOL_RANK_LOOKBACK + VOL_WINDOW + 20, len(closes) - HORIZON):
            d = dates[i]
            spot = float(closes.iloc[i])
            if spot <= 0 or pd.isna(sma.iloc[i]) or pd.isna(rv.iloc[i]) \
                    or pd.isna(vol_rank.iloc[i]):
                continue
            bullish = spot > sma.iloc[i]
            bearish = spot < sma.iloc[i]
            if vol_rank.iloc[i] < VOL_RANK_QUANTILE:
                continue  # entry rule requires elevated vol rank
            final = float(closes.iloc[i + HORIZON])
            vol_i = float(rv.iloc[i])
            rank_i = float(vol_rank.iloc[i])
            if bullish:
                self._simulate(ticker, d, "bull_put", spot, final, vol_i, rank_i, res)
            elif bearish:
                self._simulate(ticker, d, "bear_call", spot, final, vol_i, rank_i, res)

    def _simulate(self, ticker, d, side, spot, final, vol_i, rank_i, res) -> None:
        t = HORIZON / 252.0
        if side == "bull_put":
            short_k = spot * (1 - OTM_PCT)
            long_k = short_k - SPREAD_WIDTH
            credit = bs_put_premium(spot, short_k, t, vol_i) \
                - bs_put_premium(spot, long_k, t, vol_i)
        else:
            short_k = spot * (1 + OTM_PCT)
            long_k = short_k + SPREAD_WIDTH
            credit = bs_call_premium(spot, short_k, t, vol_i) \
                - bs_call_premium(spot, long_k, t, vol_i)
        max_loss = SPREAD_WIDTH - credit

        if side == "bull_put":
            pnl = credit if final > short_k else \
                (-max_loss if final < long_k else credit - (short_k - final))
        else:
            pnl = credit if final < short_k else \
                (-max_loss if final > long_k else credit - (final - short_k))
        pnl = float(np.clip(pnl, -max_loss, credit))
        # Convert per-share figures to per-contract dollars (100 shares).
        res.add(ticker=ticker, date=d.strftime("%Y-%m-%d"), side=side,
                spot=round(spot, 2), final=round(final, 2),
                vol_rank_pct=round(rank_i, 3),
                credit=round(100 * max(credit, 0.0), 2),
                max_loss=round(100 * max(max_loss, 0.0), 2),
                pnl_per_spread=round(100 * pnl, 2))


if __name__ == "__main__":
    import json
    import os

    from pathlib import Path

    logging.basicConfig(level=logging.INFO)
    bt = HistoricalBacktest()
    result = bt.run()
    print("\n========== BACKTEST REPORT ==========")
    print(json.dumps(result.metrics, indent=2, default=str))
    print("\nLast 15 trades:")
    for t in result.trades[-15:]:
        print(t)

    out_dir = Path(__file__).resolve().parents[2] / "backtest_results"
    os.makedirs(out_dir, exist_ok=True)
    with open(out_dir / "metrics.json", "w") as f:
        json.dump(result.metrics, f, indent=2, default=str)
    pd.DataFrame(result.trades).to_csv(out_dir / "trades.csv", index=False)
    print(f"\nSaved -> {out_dir}/metrics.json and trades.csv")
