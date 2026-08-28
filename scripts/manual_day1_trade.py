"""Day 1 manual vertical credit spread, end-to-end through Risk Engine + Execution Service.

Structure: SPY bull put spread, expiry 260908, short put ~755 / long put ~750 (5-wide).
Submits a single atomic mleg order and polls until it fills.
"""
import time
import uuid
import datetime as dt

from alphaswarm.data.mcp_client import MCPDataClient
from alphaswarm.engine.risk_engine import RiskEngine, SpreadTrade
from alphaswarm.engine.execution_service import ExecutionService

EXPIRY = "260908"
UNDERLYING = "SPY"
SHORT_STRIKE = 755.0
LONG_STRIKE = 750.0
CONTRACTS = 2


def get_put_quote(chain, expiry, strike):
    for sym, item in chain.items():
        from alphaswarm.data.mcp_client import parse_option_symbol
        info = parse_option_symbol(sym)
        if info and info["expiration"] == expiry and info["kind"] == "P" \
                and abs(info["strike"] - strike) < 0.001 and item.latest_quote:
            return sym, item.latest_quote.bid_price, item.latest_quote.ask_price
    return None, None, None


def main():
    c = MCPDataClient()
    chain = c.get_option_chain(UNDERLYING)
    spot = c.get_option_spot(UNDERLYING)
    print(f"spot {UNDERLYING}: {spot}")

    short_sym, short_bid, _ = get_put_quote(chain, EXPIRY, SHORT_STRIKE)
    long_sym, _, long_ask = get_put_quote(chain, EXPIRY, LONG_STRIKE)
    print("short leg:", short_sym, "bid", short_bid)
    print("long  leg:", long_sym, "ask", long_ask)
    assert short_sym and long_sym, "could not find both legs"

    credit = round(short_bid - long_ask, 2)          # conservative net credit
    limit = round(credit - 0.05, 2)                  # marketable -> fill-friendly
    print(f"net credit (fair) {credit}, limit {limit}")

    # ---- 1) Risk Engine gate ----
    trade = SpreadTrade(
        underlying=UNDERLYING, structure="bull_put_spread", expiration=EXPIRY,
        short_strike=SHORT_STRIKE, long_strike=LONG_STRIKE,
        credit_received=credit, contracts=CONTRACTS,
        short_symbol=short_sym, long_symbol=long_sym,
    )
    risk = RiskEngine()
    account = risk._client.get_account()
    equity = float(account.equity)
    print("equity:", equity, "| max_loss:", trade.max_loss())
    result = risk.check(trade, equity=equity)
    for chk in result.checks:
        print(f"  [{('PASS' if chk.passed else 'FAIL'):4}] {chk.name}: {chk.message}")
    if not result.passed:
        raise SystemExit(f"RISK ENGINE {result.summary()} -- NOT SUBMITTING")

    # ---- 2) Execution Service: build legs + submit mleg ----
    svc = ExecutionService()
    legs = svc.build_bull_put_spread(short_sym, long_sym)
    cid = f"day1-spy-bullput-{uuid.uuid4().hex[:8]}"
    order = svc.submit_spread(legs, qty=CONTRACTS, order_type="limit",
                              limit_price=limit, time_in_force="day",
                              client_order_id=cid)
    print("submitted order id:", order.id, "| status:", order.status,
          "| client_order_id:", order.client_order_id)
    if order.limit_price is not None:
        print("order limit_price (net credit):", order.limit_price)

    # ---- 3) Poll until filled ----
    filled = False
    for _ in range(60):
        o = svc._client.trading.get_order_by_id(order.id)
        print("  status:", o.status, "| filled_at:", o.filled_at, "| filled_qty:", o.filled_qty)
        if o.status in ("filled", "partially_filled"):
            filled = True
            break
        if o.status in ("canceled", "expired", "rejected"):
            print("order terminal state:", o.status)
            break
        time.sleep(5)

    print("\nFILLED:", filled)

    # ---- 4) Show resulting option position ----
    if filled:
        positions = svc._client.get_positions()
        print("\nOption positions after fill:")
        for p in positions:
            if p.asset_class == "us_option":
                print(f"  {p.symbol}: qty={p.qty} side={p.side} "
                      f"market_value={p.market_value} cost_basis={p.cost_basis} "
                      f"avg_entry={p.avg_entry_price}")


if __name__ == "__main__":
    main()
