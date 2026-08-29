"""Alpaca Operator CLI -- Ad-hoc account, position, and open order status utility.

Pitch Distinction Note:
This operator-facing CLI provides lightweight, real-time terminal sanity-checks for human monitoring,
whereas the MCP server provides structured, tool-bound market data schema pulls for autonomous agent reasoning.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any, Dict, List

from alphaswarm.data.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


def format_currency(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        f = float(val)
        return f"${f:,.2f}"
    except (ValueError, TypeError):
        return str(val)


def format_pct(val: Any) -> str:
    if val is None:
        return "N/A"
    try:
        f = float(val) * 100
        sign = "+" if f > 0 else ""
        return f"{sign}{f:.2f}%"
    except (ValueError, TypeError):
        return str(val)


def str_enum(val: Any) -> str:
    if val is None:
        return "N/A"
    s = str(getattr(val, "value", val))
    if "." in s:
        s = s.split(".")[-1]
    return s.upper()


def get_status_payload(client: AlpacaClient) -> Dict[str, Any]:
    acc = client.get_account()
    positions = client.get_positions()
    orders = client.get_orders(status="open")

    acc_dict = {
        "account_number": str(getattr(acc, "account_number", "N/A")),
        "status": str_enum(getattr(acc, "status", "N/A")),
        "equity": float(acc.equity) if hasattr(acc, "equity") and acc.equity is not None else None,
        "cash": float(acc.cash) if hasattr(acc, "cash") and acc.cash is not None else None,
        "buying_power": float(acc.buying_power) if hasattr(acc, "buying_power") and acc.buying_power is not None else None,
        "daytrading_buying_power": (
            float(acc.daytrading_buying_power)
            if hasattr(acc, "daytrading_buying_power") and acc.daytrading_buying_power is not None
            else None
        ),
        "portfolio_value": float(acc.portfolio_value) if hasattr(acc, "portfolio_value") and acc.portfolio_value is not None else None,
        "pattern_day_trader": getattr(acc, "pattern_day_trader", False),
        "trading_blocked": getattr(acc, "trading_blocked", False),
        "transfers_blocked": getattr(acc, "transfers_blocked", False),
        "account_blocked": getattr(acc, "account_blocked", False),
    }

    pos_list = []
    for p in positions:
        pos_list.append({
            "symbol": str(getattr(p, "symbol", "N/A")),
            "qty": float(p.qty) if hasattr(p, "qty") and p.qty is not None else 0.0,
            "side": str_enum(getattr(p, "side", "N/A")),
            "market_value": float(p.market_value) if hasattr(p, "market_value") and p.market_value is not None else 0.0,
            "avg_entry_price": float(p.avg_entry_price) if hasattr(p, "avg_entry_price") and p.avg_entry_price is not None else 0.0,
            "current_price": float(p.current_price) if hasattr(p, "current_price") and p.current_price is not None else 0.0,
            "unrealized_pl": float(p.unrealized_pl) if hasattr(p, "unrealized_pl") and p.unrealized_pl is not None else 0.0,
            "unrealized_plpc": float(p.unrealized_plpc) if hasattr(p, "unrealized_plpc") and p.unrealized_plpc is not None else 0.0,
            "asset_class": str_enum(getattr(p, "asset_class", "N/A")),
        })

    ord_list = []
    for o in orders:
        ord_list.append({
            "id": str(getattr(o, "id", "N/A")),
            "symbol": str(getattr(o, "symbol", "N/A")),
            "side": str_enum(getattr(o, "side", "N/A")),
            "qty": float(o.qty) if hasattr(o, "qty") and o.qty is not None else 0.0,
            "type": str_enum(getattr(o, "type", "N/A")),
            "status": str_enum(getattr(o, "status", "N/A")),
            "limit_price": float(o.limit_price) if hasattr(o, "limit_price") and o.limit_price is not None else None,
            "submitted_at": str(getattr(o, "submitted_at", "N/A")),
        })

    return {
        "account": acc_dict,
        "positions": pos_list,
        "open_orders": ord_list,
    }


def print_status_table(payload: Dict[str, Any]) -> None:
    acc = payload["account"]
    positions = payload["positions"]
    orders = payload["open_orders"]

    print("\n" + "=" * 72)
    print(" ALPACA OPERATOR ACCOUNT STATUS ")
    print("=" * 72)
    print(f" Account Number : {acc['account_number']}")
    print(f" Account Status : {acc['status']}")
    print(f" Equity         : {format_currency(acc['equity'])}")
    print(f" Cash           : {format_currency(acc['cash'])}")
    print(f" Buying Power   : {format_currency(acc['buying_power'])}")
    print(f" DT Buying Power: {format_currency(acc['daytrading_buying_power'])}")
    print(f" Portfolio Val  : {format_currency(acc['portfolio_value'])}")
    print(f" PDT Status     : {'Yes' if acc['pattern_day_trader'] else 'No'}")
    print(f" Trading Status : {'BLOCKED' if acc['trading_blocked'] or acc['account_blocked'] else 'ACTIVE'}")

    print("\n" + "-" * 72)
    print(f" OPEN POSITIONS ({len(positions)})")
    print("-" * 72)
    if not positions:
        print("  No open positions.")
    else:
        header = f"{'Symbol':<22} {'Side':<6} {'Qty':>8} {'Entry':>10} {'Current':>10} {'Mkt Value':>12} {'Unrealized PnL':>16}"
        print(header)
        print("-" * len(header))
        for p in positions:
            pnl_str = f"{format_currency(p['unrealized_pl'])} ({format_pct(p['unrealized_plpc'])})"
            print(
                f"{p['symbol']:<22} "
                f"{str(p['side']).upper():<6} "
                f"{p['qty']:>8.1f} "
                f"{p['avg_entry_price']:>10.2f} "
                f"{p['current_price']:>10.2f} "
                f"{format_currency(p['market_value']):>12} "
                f"{pnl_str:>16}"
            )

    print("\n" + "-" * 72)
    print(f" OPEN ORDERS ({len(orders)})")
    print("-" * 72)
    if not orders:
        print("  No open orders.")
    else:
        header = f"{'Order ID':<38} {'Symbol':<18} {'Side':<6} {'Qty':>6} {'Type':<8} {'Limit Price':>12} {'Status':<10}"
        print(header)
        print("-" * len(header))
        for o in orders:
            lp_str = format_currency(o['limit_price']) if o['limit_price'] is not None else "MKT"
            print(
                f"{o['id']:<38} "
                f"{o['symbol']:<18} "
                f"{o['side'].upper():<6} "
                f"{o['qty']:>6.1f} "
                f"{o['type']:<8} "
                f"{lp_str:>12} "
                f"{o['status']:<10}"
            )
    print("=" * 72 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Alpaca Operator CLI for real-time account and position status checking."
    )
    parser.add_argument("--json", action="store_true", help="Output raw JSON format instead of table.")
    parser.add_argument("--paper", action="store_true", default=True, help="Use paper trading environment (default: True).")
    parser.add_argument("--live", action="store_true", help="Use live trading environment (overrides --paper).")
    parser.add_argument("--watch", type=int, default=0, metavar="SECONDS", help="Repeatedly check status every N seconds.")

    args = parser.parse_args()

    paper = not args.live if args.live else args.paper
    client = AlpacaClient(paper=paper)

    while True:
        try:
            payload = get_status_payload(client)
            if args.json:
                print(json.dumps(payload, indent=2))
            else:
                print_status_table(payload)
        except Exception as e:
            logger.exception("Failed to retrieve operator status")
            print(f"Error fetching status: {e}", file=sys.stderr)
            if not args.watch:
                sys.exit(1)

        if args.watch <= 0:
            break
        time.sleep(args.watch)


if __name__ == "__main__":
    main()
