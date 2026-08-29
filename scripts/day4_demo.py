"""Day 4 demo: narrate ONE complete decision lifecycle end-to-end (Ideal Demo flow).

Parts 1-3: recorded Day-3 trace, live mark of the real filled SPY trade,
post-mortem (process soundness vs outcome). Parts 4-5 appended below.
"""

from __future__ import annotations

import json
import sys

from alphaswarm import decision_store
from alphaswarm.improve import imperfection_log, improvement_engine
from alphaswarm.improve.outcome_analyzer import analyze_trade, simulate_close

SECTION = "\n" + "=" * 72 + "\n  {} \n" + "=" * 72

# The real Day-1 filled trade. Entry record reconstructed from the manual
# trade log -- the orchestrator did not exist yet on Day 1, so this entry
# is hand-authored from the actual order facts, not generated.
TRADE_ENTRY = {
    "trade_id": "SPY-20260828-manual-7550-750",
    "ticker": "SPY",
    "structure": "bull_put_spread",
    "legs": [
        {"side": "short", "symbol": "SPY260908P00755000", "strike": 755.0},
        {"side": "long", "symbol": "SPY260908P00750000", "strike": 750.0},
    ],
    "contracts": 2,
    "credit_per_share": 0.53,
    "max_loss": 894.0,
    "expiration": "2026-09-08",
    "thesis": "Short-term bullish drift above SMA20/SMA50; IV cheap vs realized "
              "(10.3% realized vs 8.4-10.8% IV); 7 DTE premium sale, defined risk.",
    "information_available": [
        "market agent: trending_up / bullish, conf 0.70",
        "volatility agent: low regime, IV cheap, conf 0.90",
        "options agent: real bid/ask surface, tight spreads",
        "portfolio agent: existing SPY 755/750 overlap flagged, proceed_with_caution",
    ],
    "conditions": [
        {"condition": "spot above short strike 755 at mark", "held": None},
        {"condition": "no IV spike event before expiry", "held": None},
    ],
}


def load_last_trace() -> dict | None:
    """Parse the last decision cycle from the JSONL (multi-doc JSON)."""
    try:
        text = open(decision_store.DEFAULT_PATH, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    dec, traces = json.JSONDecoder(), []
    i = 0
    while i < len(text):
        obj, j = dec.raw_decode(text, i)
        traces.append(obj)
        i = j
        while i < len(text) and text[i] in " \n\r\t":
            i += 1
    return traces[-1] if traces else None


def step_open_position_and_postmortem() -> dict | None:
    print(SECTION.format("STEP 2-3 -- OPEN POSITION, LIVE MARK, POST-MORTEM"))
    print(f"trade: {TRADE_ENTRY['trade_id']}")
    print(f"structure: {TRADE_ENTRY['structure']} x{TRADE_ENTRY['contracts']} "
          f"({TRADE_ENTRY['legs'][0]['symbol']} / {TRADE_ENTRY['legs'][1]['symbol']})")
    print(f"entry credit: ${TRADE_ENTRY['credit_per_share']}/share, "
          f"max loss ${TRADE_ENTRY['max_loss']}, expiry {TRADE_ENTRY['expiration']}")

    outcome = simulate_close(TRADE_ENTRY)
    if "error" in outcome:
        print("LIVE MARK UNAVAILABLE:", outcome["error"])
        print("-> post-mortem blocked; not faking data")
        return None
    print(f"mark: close cost ${outcome['close_cost_per_share']}/share -> "
          f"unrealized P/L ${outcome['pnl_unrealized']} "
          f"({outcome['pct_of_max_profit']:.0%} of max profit)")
    print("caveat:", outcome["caveat"])

    # Condition 1 needs the underlying spot, not option marks.
    from alphaswarm.data.alpaca_client import AlpacaClient
    spot = AlpacaClient().get_option_spot_price("SPY")
    TRADE_ENTRY["conditions"][0]["held"] = spot is not None and spot > 755
    TRADE_ENTRY["conditions"][1]["held"] = outcome["pct_of_max_profit"] < 1.0
    print(f"spot check: SPY at {spot} vs short strike 755 -> "
          f"condition held={TRADE_ENTRY['conditions'][0]['held']}")
    postmortem = analyze_trade(TRADE_ENTRY, outcome)
    print(json.dumps(postmortem, indent=2, default=str))
    return postmortem


def step_decision_trace() -> None:
    print(SECTION.format("STEP 1 -- DECISION LIFECYCLE (recorded Day-3 trace)"))
    trace = load_last_trace()
    if not trace:
        print("no decision trace found -- narrating the manual Day-1 trade only")
        return
    print("ticker:", trace.get("ticker", "?"))
    print("stages recorded:", [k for k in trace.keys()
                               if k not in ("recorded_at", "cycle_id", "ticker")])
    mentor = trace.get("mentor_audit_v1") or {}
    print("mentor decision:", mentor.get("overall_decision", "n/a"),
          "| imperfections:", len(mentor.get("imperfections", [])))
    for k in ("final_decision", "final", "outcome"):
        if k in trace:
            print(f"{k}:", trace[k])


def step_imperfection_log() -> None:
    print(SECTION.format("STEP 4 -- IMPERFECTION LOG (Section 21 table)"))
    if not imperfection_log.load():
        imperfection_log.seed_initial_observations()
        print("(seeded initial manual observations from Days 1-3)")
    for agent, s in imperfection_log.per_agent_summary().items():
        print(f"\n{agent}  (n={s['n_observations']})")
        print(f"  strengths:   {'; '.join(sorted(set(s['strengths']))) or '-'}")
        print(f"  weaknesses:  {'; '.join(sorted(set(s['weaknesses']))) or '-'}")
    print("\nNOTE: n is far too small for statistical claims; running "
          "qualitative table only.")


def step_improvement_loop(skip_llm: bool) -> None:
    print(SECTION.format("STEP 5 -- IMPROVEMENT LOOP (mechanism demo)"))
    hyp = improvement_engine.generate_hypothesis()
    if hyp is None:
        print("no signal in log; nothing to review")
        return
    print("hypothesis (deterministic pick from log):")
    print(json.dumps(hyp, indent=2))
    if skip_llm:
        print("\n[--skip-llm] Mentor review skipped.")
        return
    print("\nsending to Mentor (Nemotron) for review...")
    review = improvement_engine.review_hypothesis(hyp)
    print(json.dumps(review, indent=2))
    version_rec = improvement_engine.record_version(hyp, review)
    print("\nversion record written to versions.jsonl:")
    print(json.dumps(version_rec, indent=2))
    print(f"\n  (promotion_decision: {version_rec['promotion_decision']})")
    print("\nNOTE: mechanism demo only -- sample size does not support "
          "treating this as a validated improvement.")


def main() -> None:
    skip_llm = "--skip-llm" in sys.argv
    step_decision_trace()
    step_open_position_and_postmortem()
    step_imperfection_log()
    step_improvement_loop(skip_llm)
    print(SECTION.format("DEMO COMPLETE"))


if __name__ == "__main__":
    main()
