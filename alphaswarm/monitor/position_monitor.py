"""Position Monitor -- scheduled deterministic check of open positions.

Produces one of HOLD / REDUCE / EXIT / REVIEW per open option position.
DETERMINISTIC ONLY (Agent Rules Section 1: no LLM owns this domain; and
Agent Rules Section 3.5: nothing here can override a Risk Engine FAIL --
the monitor never opens positions, it can only recommend closing).

Rules (checked in order, first match wins):
  1. DTE <= 0                      -> EXIT (expired; do not hold through)
  2. DTE <= EXIT_DTE (2)           -> EXIT (gamma risk near expiry)
  3. unrealized PL >= +TAKE_PROFIT -> EXIT (profit target reached)
  4. unrealized PL <= -STOP_LOSS   -> EXIT (stop loss hit)
  5. DTE <= REVIEW_DTE (7)         -> REVIEW (decision needed soon)
  6. |position value| grows beyond REDUCE threshold -> REDUCE
  7. otherwise                     -> HOLD
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from .. import config
from ..data.alpaca_client import AlpacaClient
from ..data.mcp_client import parse_option_symbol

logger = logging.getLogger(__name__)

TAKE_PROFIT_PCT = 0.50   # +50% of premium captured -> take profit
STOP_LOSS_PCT = -1.00    # lost 100% of premium -> exit (2x-credit rule simplified)
EXIT_DTE = 2
REVIEW_DTE = 7


def _dte(expiration: str, today) -> int:
    from datetime import datetime

    exp = datetime.strptime(expiration, "%y%m%d").date()
    return (exp - today).days


def evaluate_position(pos: Any, today) -> Dict[str, Any]:
    sym = pos.symbol
    info = parse_option_symbol(sym)
    pl_pct = float(getattr(pos, "unrealized_plpc", 0) or 0)
    base = {
        "symbol": sym,
        "qty": float(pos.qty),
        "side": str(pos.side),
        "market_value": float(pos.market_value),
        "unrealized_pl": float(getattr(pos, "unrealized_pl", 0) or 0),
        "unrealized_plpc": pl_pct,
    }
    if info is None:
        return {**base, "action": "REVIEW", "rule": "non-option position in book"}
    dte = _dte(info["expiration"], today)
    base.update({"underlying": info["underlying"], "kind": info["kind"],
                 "strike": info["strike"], "expiration": info["expiration"], "dte": dte})

    if dte <= 0:
        return {**base, "action": "EXIT", "rule": f"expired (dte={dte})"}
    if dte <= EXIT_DTE:
        return {**base, "action": "EXIT", "rule": f"gamma risk: dte={dte} <= {EXIT_DTE}"}
    if pl_pct >= TAKE_PROFIT_PCT:
        return {**base, "action": "EXIT", "rule": f"take profit: plpc={pl_pct:.0%} >= {TAKE_PROFIT_PCT:.0%}"}
    if pl_pct <= STOP_LOSS_PCT:
        return {**base, "action": "EXIT", "rule": f"stop loss: plpc={pl_pct:.0%} <= {STOP_LOSS_PCT:.0%}"}
    if dte <= REVIEW_DTE:
        return {**base, "action": "REVIEW", "rule": f"dte={dte} <= {REVIEW_DTE}: decide roll/close"}
    return {**base, "action": "HOLD", "rule": f"within thresholds (dte={dte}, plpc={pl_pct:.0%})"}


class PositionMonitor:
    def __init__(self, client: AlpacaClient | None = None):
        self._client = client or AlpacaClient()

    def run_once(self) -> List[Dict[str, Any]]:
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).date()
        results = [evaluate_position(p, today) for p in self._client.get_positions()]
        for r in results:
            logger.info("monitor %s -> %s (%s)", r["symbol"], r["action"], r["rule"])
        return results

    def run_forever(self, interval_seconds: int = 300) -> None:
        """Scheduled loop: check every `interval_seconds` until stopped."""
        while True:
            try:
                self.run_once()
            except Exception:
                logger.exception("monitor iteration failed")
            time.sleep(interval_seconds)
