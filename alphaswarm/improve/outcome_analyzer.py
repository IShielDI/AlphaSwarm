"""Outcome Analyzer -- structured post-mortem per closed trade (TRD Section 4
decision data model).

Core principle: judge the DECISION, not just the P/L. Was the trade sound
given the information available at entry? A good process can lose money and
a bad process can win -- conflating the two is how trading systems learn
the wrong lessons.

DETERMINISTIC ONLY: no LLM calls. With a sample size of one real trade, any
"learned" conclusion must stay a hypothesis candidate for the imperfection
log / improvement engine, never a validated finding.

The only real fill so far (Day 1 manual SPY 755/750 bull put, exp 260908)
has NOT closed naturally -- it is still open. This module therefore supports
simulated mark-to-market closes, clearly labeled as such.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..data.alpaca_client import AlpacaClient

logger = logging.getLogger(__name__)


def _mark_positions(symbols: List[str], client: AlpacaClient) -> Dict[str, Dict[str, Any]]:
    """Current bid/ask/last per leg symbol from live Alpaca option snapshots."""
    marks: Dict[str, Dict[str, Any]] = {}
    if not symbols:
        return marks
    try:
        from alpaca.data.requests import OptionSnapshotRequest

        snap = client.option_data.get_option_snapshot(
            OptionSnapshotRequest(symbol_or_symbols=symbols)
        )
    except Exception as e:  # snapshot failure must not crash the post-mortem
        logger.warning("option snapshot failed: %s", e)
        return marks
    for sym in symbols:
        item = snap.get(sym) if hasattr(snap, "get") else None
        if item is None:
            continue
        q = item.latest_quote
        marks[sym] = {
            "bid": float(q.bid_price) if q and q.bid_price else None,
            "ask": float(q.ask_price) if q and q.ask_price else None,
            "last": float(item.latest_trade.price) if item.latest_trade else None,
        }
    return marks


def simulate_close(entry: Dict[str, Any], client: AlpacaClient | None = None) -> Dict[str, Any]:
    """Mark a credit spread to market and compute unrealized P/L.

    Cost to close = (short bid - long ask) per share (buy back the spread).
    P/L = (entry_credit - close_cost) * 100 * contracts.
    """
    client = client or AlpacaClient()
    legs = entry["legs"]
    symbols = [leg["symbol"] for leg in legs]
    marks = _mark_positions(symbols, client)
    if len(marks) < len(symbols):
        return {"error": f"missing live marks for {sorted(set(symbols) - set(marks))}"}

    short_sym = next(l["symbol"] for l in legs if l["side"] == "short")
    long_sym = next(l["symbol"] for l in legs if l["side"] == "long")
    short_bid = marks[short_sym].get("bid")
    long_ask = marks[long_sym].get("ask")
    if short_bid is None or long_ask is None:
        return {"error": "incomplete quotes for close valuation", "marks": marks}

    close_cost = round(short_bid - long_ask, 2)
    contracts = entry["contracts"]
    entry_credit = entry["credit_per_share"]
    pnl = round((entry_credit - close_cost) * 100 * contracts, 2)
    max_profit = round(entry_credit * 100 * contracts, 2)
    return {
        "close_type": "simulated_mark_to_market",
        "marked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "marks": marks,
        "close_cost_per_share": close_cost,
        "entry_credit_per_share": entry_credit,
        "pnl_unrealized": pnl,
        "max_profit_if_expiry_worthless": max_profit,
        "pct_of_max_profit": round(pnl / max_profit, 4) if max_profit else None,
        "caveat": "SIMULATED close at current mark, not an actual fill; a real exit "
                  "would cross the spread and may slip",
    }


def analyze_trade(entry: Dict[str, Any], outcome: Dict[str, Any]) -> Dict[str, Any]:
    """Post-mortem: process assessment vs outcome, per the decision data model.

    `entry` needs: trade_id, ticker, structure, legs, contracts,
    credit_per_share, max_loss, thesis, information_available (what was
    known at entry), conditions (list of {condition, held} checks).
    `outcome` is simulate_close() output (or an actual close record).
    """
    if "error" in outcome:
        return {"trade_id": entry.get("trade_id"), "error": outcome["error"],
                "note": "post-mortem blocked on live marks; retry when quotes exist"}

    conditions = entry.get("conditions", [])
    held = [c for c in conditions if c.get("held")]
    broken = [c for c in conditions if not c.get("held")]
    # Process soundness: deterministic checks on facts known at entry.
    process_checks = [
        {"check": "structure in allowed set (vertical credit spreads only)",
         "passed": entry.get("structure") in ("bull_put_spread", "bear_call_spread")},
        {"check": "entry had explicit exit/invalidation conditions",
         "passed": bool(conditions)},
        {"check": "max loss was quantified before entry",
         "passed": isinstance(entry.get("max_loss"), (int, float))
                   and entry.get("max_loss", 0) > 0},
        {"check": "no entry thesis condition broken at mark time",
         "passed": len(broken) == 0},
    ]
    decision_sound = all(c["passed"] for c in process_checks)

    pnl = outcome.get("pnl_unrealized")
    profitable = pnl is not None and pnl > 0
    quadrant = (
        "sound process + favorable outcome" if decision_sound and profitable else
        "sound process + unfavorable outcome (do not punish the process)"
        if decision_sound else
        "flawed process + favorable outcome (do not reward the luck)"
        if profitable else
        "flawed process + unfavorable outcome"
    )
    return {
        "trade_id": entry.get("trade_id"),
        "ticker": entry.get("ticker"),
        "structure": entry.get("structure"),
        "analyzed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "entry_summary": {
            "legs": entry.get("legs"),
            "contracts": entry.get("contracts"),
            "credit_per_share": entry.get("credit_per_share"),
            "max_loss": entry.get("max_loss"),
        },
        "process_assessment": {
            "information_available_at_entry": entry.get("information_available", []),
            "thesis": entry.get("thesis"),
            "checks": process_checks,
            "conditions_held": held,
            "conditions_broken": broken,
            "decision_sound": decision_sound,
            "note": "soundness judged on process facts and the information available "
                    "at entry -- NOT on whether the trade made money",
        },
        "outcome": outcome,
        "process_vs_outcome": quadrant,
        "lesson_candidates": _lesson_candidates(entry, outcome, decision_sound,
                                                profitable),
    }


def _lesson_candidates(entry, outcome, decision_sound, profitable) -> List[Dict[str, Any]]:
    """Candidate entries for the imperfection log (hypotheses, not findings)."""
    cands: List[Dict[str, Any]] = []
    if decision_sound:
        cands.append({
            "owner": "strategist",
            "area": "entry process",
            "note": f"All process checks passed; "
                    f"{'favorable' if profitable else 'unfavorable'} mark so far. Keep "
                    "the process unchanged; accumulate more samples before drawing "
                    "any conclusion (n=1).",
        })
    else:
        for c in entry.get("conditions", []):
            if not c.get("held"):
                cands.append({
                    "owner": c.get("owner", "strategist"),
                    "area": c.get("owner_area", "entry conditions"),
                    "note": f"Condition broken at mark time: {c.get('condition')}",
                })
    cands.append({
        "owner": "position_monitor",
        "area": "exit timing",
        "note": f"Mark-based P/L is {outcome.get('pct_of_max_profit')} of max profit; "
                "monitor thresholds (TP +50%, SL -100%, EXIT by DTE 2) govern the "
                "actual exit -- the post-mortem does not second-guess them.",
    })
    return cands
