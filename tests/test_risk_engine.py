"""Unit tests for the deterministic Risk Engine (no live network needed)."""
from alphaswarm.engine.risk_engine import RiskEngine, SpreadTrade


class _Pos:
    def __init__(self, symbol, market_value):
        self.symbol = symbol
        self.market_value = market_value


def test_max_loss_respects_cap():
    eng = RiskEngine()
    # width 5, credit 1.00/share, 2 contracts -> loss (5-1)*100*2 = 800
    t = SpreadTrade("SPY", "bull_put_spread", "260918", 760, 755, 1.0, 2)
    c = eng._check_max_loss(t, 100_000)
    print("max_loss check passed:", c.passed, "|", c.message)
    assert c.passed


def test_oversized_rejected():
    eng = RiskEngine()
    # width 20, credit 1.00/share, 40 contracts -> loss 19*100*40 = 76,000 > 2% equity
    t = SpreadTrade("SPY", "bull_put_spread", "260918", 760, 740, 1.0, 40)
    r = eng.check(t, equity=100_000, existing_positions=[])
    print("oversized summary:", r.summary())
    assert not r.passed
    assert "max_loss" in r.failed_checks or "position_size" in r.failed_checks


def test_duplicate_detected():
    eng = RiskEngine()
    t = SpreadTrade("SPY", "bull_put_spread", "260918", 760, 755, 1.0, 2)
    positions = [_Pos("SPY260918P00760000", 2000)]  # same short strike/expiry
    r = eng.check(t, equity=100_000, existing_positions=positions)
    print("duplicate summary:", r.summary())
    assert not r.passed
    assert "duplicate_order" in r.failed_checks


def test_duplicate_not_same_strike_is_fine():
    eng = RiskEngine()
    t = SpreadTrade("SPY", "bull_put_spread", "260918", 760, 755, 1.0, 2)
    positions = [_Pos("SPY260918P00770000", 2000)]  # different short strike
    r = eng.check(t, equity=100_000, existing_positions=positions)
    print("non-dup summary:", r.summary())
    assert r.passed


if __name__ == "__main__":
    test_max_loss_respects_cap()
    test_oversized_rejected()
    test_duplicate_detected()
    test_duplicate_not_same_strike_is_fine()
    print("ALL RISK ENGINE TESTS PASSED")