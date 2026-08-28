"""Execution Service -- multi-leg order construction and submission.

Per TRD Section 2.2 / 2.3 and Agent Rules Section 3.1:
  * Every spread is one atomic order with order_class="mleg" and a `legs`
    array -- never two separate single-leg orders.
  * Each leg specifies symbol, side, ratio qty, and position intent
    (buy_to_open / sell_to_open).
  * HARD CONSTRAINT enforced before submission: every short leg must be
    covered by a long leg within the same order (vertical credit spreads
    satisfy this by construction; we verify it regardless).

This component makes no LLM calls. Anything reaching Alpaca must pass the
Risk Engine first (enforced by the caller / orchestrator).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from alpaca.trading.enums import OrderClass, OrderSide, OrderType, TimeInForce
from alpaca.trading.requests import OptionLegRequest, OrderRequest
from alpaca.trading.enums import PositionIntent

from ..data.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


class WrongLegRatioError(ValueError):
    pass


class UncoveredShortError(ValueError):
    pass


class ExecutionService:
    """Constructs and submits multi-leg (mleg) vertical credit spreads."""

    def __init__(self, client: Optional[AlpacaClient] = None) -> None:
        self._client = client or AlpacaClient()

    # ------------------------------------------------------------------
    # Leg construction
    # ------------------------------------------------------------------
    def build_bull_put_spread(
        self,
        short_symbol: str,
        long_symbol: str,
    ) -> List[OptionLegRequest]:
        """Bull put: sell OTM put (short) + buy further-OTM put (protective).

        ratio_qty is 1 on every leg (Alpaca requires relatively-prime ratios);
        the contract count is set via the order's top-level `qty`.
        """
        return [
            OptionLegRequest(
                symbol=short_symbol,
                ratio_qty=1.0,
                side=OrderSide.SELL,
                position_intent=PositionIntent.SELL_TO_OPEN,
            ),
            OptionLegRequest(
                symbol=long_symbol,
                ratio_qty=1.0,
                side=OrderSide.BUY,
                position_intent=PositionIntent.BUY_TO_OPEN,
            ),
        ]

    def build_bear_call_spread(
        self,
        short_symbol: str,
        long_symbol: str,
    ) -> List[OptionLegRequest]:
        """Bear call: sell OTM call (short) + buy further-OTM call (protective)."""
        return [
            OptionLegRequest(
                symbol=short_symbol,
                ratio_qty=1.0,
                side=OrderSide.SELL,
                position_intent=PositionIntent.SELL_TO_OPEN,
            ),
            OptionLegRequest(
                symbol=long_symbol,
                ratio_qty=1.0,
                side=OrderSide.BUY,
                position_intent=PositionIntent.BUY_TO_OPEN,
            ),
        ]

    # ------------------------------------------------------------------
    # Validation (short legs must be covered within the same order)
    # ------------------------------------------------------------------
    def validate_spread(
        self, legs: List[OptionLegRequest], max_side_ratio: float = 1.0
    ) -> int:
        """Validate `legs` for defined-risk coverage; returns the contract count.

        Enforces the TRD 2.2 hard constraint: every short leg must be covered
        by a long leg in the same order. Rejects any structure with more short
        contracts than long contracts (uncovered short) or unbalanced ratios.
        """
        shorts = [l for l in legs if l.side == OrderSide.SELL]
        longs = [l for l in legs if l.side == OrderSide.BUY]
        if not longs:
            raise UncoveredShortError(
                "spread has short legs but no long (protective) leg in the order"
            )
        short_qty = sum(l.ratio_qty for l in shorts)
        long_qty = sum(l.ratio_qty for l in longs)
        if short_qty > long_qty * max_side_ratio:
            raise UncoveredShortError(
                f"uncovered short: short qty {short_qty} > long qty {long_qty}"
            )
        if not all(l.ratio_qty > 0 for l in legs):
            raise WrongLegRatioError("all leg ratio_qty must be > 0")
        # All legs must share the same quantity (defined-risk 1:1 spread).
        qty = legs[0].ratio_qty
        if not all(abs(l.ratio_qty - qty) < 1e-9 for l in legs):
            raise WrongLegRatioError(
                "all legs must have equal ratio_qty for a defined-risk spread"
            )
        return int(qty)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def submit_spread(
        self,
        legs: List[OptionLegRequest],
        qty: int,
        order_type: str = "limit",
        limit_price: Optional[float] = None,
        time_in_force: str = "day",
        client_order_id: Optional[str] = None,
    ):
        """Construct and submit a single atomic multi-leg order.

        Runs validate_spread first (throws on uncovered/Invalid legs). `qty` is
        the number of contracts (top-level order qty; leg ratio_qty stays 1).
        Returns the raw order response (with .id / .status / .client_order_id).
        """
        self.validate_spread(legs)
        if qty <= 0:
            raise ValueError("qty must be > 0")

        order_type = OrderType(order_type)
        if order_type == OrderType.LIMIT and limit_price is None:
            raise ValueError("limit orders require a net limit_price")

        common = dict(
            order_class=OrderClass.MLEG,
            type=order_type,
            qty=float(qty),
            time_in_force=TimeInForce(time_in_force),
            legs=legs,
            client_order_id=client_order_id,
        )
        if order_type == OrderType.LIMIT:
            # LimitOrderRequest carries limit_price; plain OrderRequest drops it.
            from alpaca.trading.requests import LimitOrderRequest

            order_req = LimitOrderRequest(limit_price=limit_price, **common)
        else:
            order_req = OrderRequest(**common)
        return self._client.trading.submit_order(order_req)
