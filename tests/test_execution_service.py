"""Unit tests for Execution Service validation logic (no live submission)."""
from alpaca.trading.enums import OrderSide, PositionIntent
from alpaca.trading.requests import OptionLegRequest

from alphaswarm.engine.execution_service import (
    ExecutionService,
    UncoveredShortError,
    WrongLegRatioError,
)


def _leg(symbol, side, qty, intent):
    return OptionLegRequest(
        symbol=symbol, ratio_qty=float(qty), side=side, position_intent=intent
    )


def test_valid_bull_put_spread():
    svc = ExecutionService()
    legs = svc.build_bull_put_spread(
        short_symbol="SPY260918P00755000",
        long_symbol="SPY260918P00750000",
    )
    qty = svc.validate_spread(legs)
    print("bull put valid, leg ratio qty =", qty)
    assert qty == 1
    # contracts go on the order-level qty, not the leg ratio
    assert all(l.ratio_qty == 1.0 for l in legs)


def test_uncovered_short_rejected():
    svc = ExecutionService()
    legs = [
        _leg("SPY260918P00755000", OrderSide.SELL, 2, PositionIntent.SELL_TO_OPEN),
    ]
    try:
        svc.validate_spread(legs)
        raise AssertionError("should have raised")
    except UncoveredShortError as e:
        print("uncovered short rejected:", e)


def test_unbalanced_ratio_rejected():
    svc = ExecutionService()
    legs = [
        _leg("SPY260918P00755000", OrderSide.SELL, 2, PositionIntent.SELL_TO_OPEN),
        _leg("SPY260918P00750000", OrderSide.BUY, 1, PositionIntent.BUY_TO_OPEN),
    ]
    try:
        svc.validate_spread(legs)
        raise AssertionError("should have raised")
    except (UncoveredShortError, WrongLegRatioError) as e:
        print("unbalanced ratio rejected:", e)


if __name__ == "__main__":
    test_valid_bull_put_spread()
    test_uncovered_short_rejected()
    test_unbalanced_ratio_rejected()
    print("ALL EXECUTION SERVICE VALIDATION TESTS PASSED")