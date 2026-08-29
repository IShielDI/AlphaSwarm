"""Imperfection Log -- running per-agent performance table (design doc
Section 21 format: agent name, strength area, weak area).

A plain append-only JSONL file (imperfections_log.jsonl), NOT a database.
Entries come from three sources: Mentor audit outputs (Day 3), the
Outcome Analyzer's lesson candidates, and human observations. Each entry
is an OBSERVATION, not a statistically validated finding -- sample sizes
are far too small for that.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        os.pardir, "imperfections_log.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def append(agent: str, strength_area: str, weak_area: str, source: str,
           note: str = "", path: str | None = None) -> Dict[str, Any]:
    entry = {
        "recorded_at": _now(),
        "agent": agent,
        "strength_area": strength_area,
        "weak_area": weak_area,
        "source": source,
        "note": note,
    }
    p = path or LOG_PATH
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def load(path: str | None = None) -> List[Dict[str, Any]]:
    p = path or LOG_PATH
    if not os.path.exists(p):
        return []
    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def per_agent_summary(path: str | None = None) -> Dict[str, Dict[str, Any]]:
    """Section 21 table: agent -> {strengths, weaknesses, n_observations}."""
    table: Dict[str, Dict[str, Any]] = {}
    for e in load(path):
        row = table.setdefault(e["agent"], {"strengths": [], "weaknesses": [],
                                            "n_observations": 0})
        if e.get("strength_area"):
            row["strengths"].append(e["strength_area"])
        if e.get("weak_area"):
            row["weaknesses"].append(e["weak_area"])
        row["n_observations"] += 1
    return table


def seed_initial_observations(path: str | None = None) -> List[Dict[str, Any]]:
    """Seed the log with documented observations from Days 1-3 (once).

    Every entry cites where it came from. All are single-observation
    anecdotes -- explicitly NOT validated findings.
    """
    if load(path):
        return []  # already seeded
    seeded = [
        ("strategist", "faithful synthesis of all four Layer-1 outputs; explicit "
         "alternatives-considered and honest reasons_not_to_trade",
         "NO_TRADE over-caution when Portfolio flags any conflict, even minor ones "
         "(4/4 real snapshots went NO_TRADE); IV interpretation for credit selling "
         "was inverted once (fixed in d59fc76, unvalidated)"),
        ("market_agent", "evidence-grounded regime calls; cited actual price data in "
         "every supporting/contradictory point",
         "none observed yet"),
        ("volatility_agent", "clear IV-vs-realized-vol framing with term structure",
         "surfaced a data anomaly (spot=0.0) as a warning instead of failing hard -- "
         "correct behavior, but downstream agents were not told to halt"),
        ("options_agent", "used only real Alpaca quotes/symbols; leg-strike "
         "direction validated every run",
         "expiry selection picked 2-DTE contracts under steep backwardation (NVDA), "
         "where IV/liquidity is noisiest"),
        ("portfolio_agent", "detected real overlapping-strike conflict with the open "
         "Day-1 position",
         "none observed yet"),
        ("mentor", "mandatory component-by-component decomposition produced "
         "owner-attributable imperfections (4/4 standalone schema-exact)",
         "slow (150-240s per audit) and needed max_tokens raised -- reasoning "
         "tokens once exhausted the response budget"),
        ("position_monitor", "deterministic, threshold-based, no LLM failure modes",
         "none observed yet"),
    ]
    out = []
    for agent, strength, weak in seeded:
        out.append(append(agent, strength, weak,
                          source="days1-3_manual_observation",
                          note="single-observation anecdote, NOT a validated finding",
                          path=path))
    return out
