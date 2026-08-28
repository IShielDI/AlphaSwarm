"""Deterministic Risk Engine.

A hard safety boundary (PRD Section 4; TRD Section 5; Agent Rules Section
3.5): pure Python, ZERO LLM calls, and no agent -- including the Mentor --
can override a Risk Engine FAIL.

Checks (hard-coded rules, not prompts):
  1. Max loss per trade        -- max_loss <= MAX_LOSS_PER_TRADE_PCT * equity
  2. Position size             -- contracts within MAX_CONTRACTS_PER_LEG and
                                  spread width notional <= MAX_PREMIUM_NOTIONAL_PCT
  3. Portfolio concentration   -- at-risk exposure in `underlying` (open
                                  positions + this trade) <= concentration cap
  4. Duplicate-order prevention-- refuse a spread already open on the same
                                  underlying/expiration/structure/strikes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

from .. import config
from ..data.alpaca_client import AlpacaClient
from ..data.mcp_client import parse_option_symbol

logger = logging.getLogger(__name__)

OPTION_MULTIPLIER = 100


@dataclass
class SpreadTrade:
    """Minimal set of fields the Risk Engine needs (deterministic)."""

    underlying: str
    structure: str            # "bull_put_spread" | "bear_call_spread"
    expiration: str           # YYMMDD
    short_strike: float
    long_strike: float
    credit_received: float    # net credit per share
    contracts: int
    long_symbol: Optional[str] = None
    short_symbol: Optional[str] = None

    @property
    def spread_width(self) -> float:
        return abs(self.short_strike - self.long_strike)

    def max_loss(self) -> float:
        """Max dollar loss for the whole trade on a to-max-loss move."""
        per_share = self.spread_width - self.credit_received
        if per_share < 0.0:
            per_share = 0.0
        return per_share * OPTION_MULTIPLIER * self.contracts

    @property
    def spread_notional(self) -> float:
        """Width-based at-risk notional (margin proxy) for the whole trade."""
        return self.spread_width * OPTION_MULTIPLIER * self.contracts

    def fingerprint(self) -> str:
        return (
            f"{self.underlying.upper()}|{self.expiration}|{self.structure}|"
            f"{self.short_strike}|{self.long_strike}"
        )

@dataclass
class RiskCheck:
    name: str
    passed: bool
    message: str


@dataclass
class RiskResult:
    passed: bool
    checks: List[RiskCheck] = field(default_factory=list)

    @property
    def failed_checks(self) -> List[str]:
        return [c.name for c in self.checks if not c.passed]

    def summary(self) -> str:
        return "PASS" if self.passed else f"FAIL({', '.join(self.failed_checks)})"


class RiskEngine:
    """Deterministic, no-LLM gate that must run before any order is submitted."""

    def __init__(self, client: Optional[AlpacaClient] = None) -> None:
        self._client = client or AlpacaClient()

    def check(
        self,
        trade: SpreadTrade,
        equity: float,
        existing_positions: Optional[List] = None,
    ) -> RiskResult:
        """Run all checks; equity/positions fetched live unless injected."""
        if existing_positions is None:
            existing_positions = self._client.get_positions()

        checks = [
            self._check_max_loss(trade, equity),
            self._check_position_size(trade, equity),
            self._check_concentration(trade, equity, existing_positions),
            self._check_duplicate(trade, existing_positions),
        ]
        return RiskResult(passed=all(c.passed for c in checks), checks=checks)

    def _check_max_loss(self, trade: SpreadTrade, equity: float) -> RiskCheck:
        ml = trade.max_loss()
        cap = config.MAX_LOSS_PER_TRADE_PCT * equity
        if ml <= 0.0:
            return RiskCheck(
                "max_loss", False,
                f"non-positive max loss ({ml:.2f}); cannot size an inverted "
                f"credit spread",
            )
        if ml > cap:
            return RiskCheck(
                "max_loss", False,
                f"max loss ${ml:,.0f} exceeds {config.MAX_LOSS_PER_TRADE_PCT:.0%} "
                f"equity cap ${cap:,.0f}",
            )
        return RiskCheck("max_loss", True, f"max loss ${ml:,.0f} within ${cap:,.0f}")

    def _check_position_size(self, trade: SpreadTrade, equity: float) -> RiskCheck:
        if trade.contracts > config.MAX_CONTRACTS_PER_LEG:
            return RiskCheck(
                "position_size", False,
                f"{trade.contracts} contracts exceeds cap "
                f"{config.MAX_CONTRACTS_PER_LEG}",
            )
        cap = config.MAX_PREMIUM_NOTIONAL_PCT * equity
        if trade.spread_notional > cap:
            return RiskCheck(
                "position_size", False,
                f"width notional ${trade.spread_notional:,.0f} exceeds "
                f"${cap:,.0f}",
            )
        return RiskCheck(
            "position_size", True,
            f"{trade.contracts} contracts, notional ${trade.spread_notional:,.0f}",
        )

    # ------------------------------------------------------------------
    # 3. Portfolio concentration
    # ------------------------------------------------------------------
    def _check_concentration(self, trade: SpreadTrade, equity: float,
                             positions: List) -> RiskCheck:
        at_risk = self._underlying_exposure(positions, trade.underlying)
        at_risk += trade.max_loss()
        cap = config.MAX_CONCENTRATION_PER_UNDERLYING_PCT * equity
        if at_risk > cap:
            return RiskCheck(
                "concentration", False,
                f"at-risk in {trade.underlying} ${at_risk:,.0f} exceeds "
                f"${cap:,.0f} cap",
            )
        return RiskCheck(
            "concentration", True,
            f"at-risk in {trade.underlying} ${at_risk:,.0f} within ${cap:,.0f}",
        )

    @staticmethod
    def _underlying_exposure(positions: List, underlying: str) -> float:
        total = 0.0
        for p in positions:
            sym = getattr(p, "symbol", None)
            mv = getattr(p, "market_value", None)
            if not sym or mv is None:
                continue
            info = parse_option_symbol(sym)
            if info and info["underlying"].upper() == underlying.upper():
                total += abs(float(mv))
        return total

    # ------------------------------------------------------------------
    # 4. Duplicate-order prevention
    # ------------------------------------------------------------------
    def _check_duplicate(self, trade: SpreadTrade, positions: List) -> RiskCheck:
        fp = trade.fingerprint()
        for p in positions:
            sym = getattr(p, "symbol", None)
            if not sym:
                continue
            info = parse_option_symbol(sym)
            if info is None:
                continue
            same_side = (
                (trade.structure == "bull_put_spread" and info["kind"] == "P")
                or (trade.structure == "bear_call_spread" and info["kind"] == "C")
            )
            if (
                info["underlying"].upper() == trade.underlying.upper()
                and info["expiration"] == trade.expiration
                and same_side
                and abs(info["strike"] - trade.short_strike) < 0.001
            ):
                return RiskCheck(
                    "duplicate_order", False,
                    f"spread already open: {sym} matches {fp}",
                )
        return RiskCheck("duplicate_order", True, f"no duplicate of {fp}")