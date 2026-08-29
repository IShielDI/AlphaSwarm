"""Lightweight retrieval of past decisions by tag matching.

Given current situation tags (ticker, market regime, volatility regime),
searches ``decisions.jsonl`` (decision_store) and ``imperfections_log.jsonl``
(imperfection_log) for past decisions with matching or similar tags.
Returns short summaries (situation, what was decided, what the Mentor flagged,
the outcome if known).

NO embeddings or vector store -- simple keyword/exact-tag matching over the
existing JSONL logs is sufficient given the current data volume.  This is
framed as a working mechanism that becomes more valuable as trade volume grows,
NOT as proven experience-based improvement at the current sample size.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from ..decision_store import DEFAULT_PATH as DECISIONS_PATH
from . import imperfection_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_decision_traces(path: str | None = None) -> List[Dict[str, Any]]:
    """Load all decision records from the JSONL (multi-doc JSON) file.

    decisions.jsonl uses indent=2 pretty-printing (multiple lines per object),
    so we parse consecutive top-level JSON objects rather than line-by-line.
    """
    p = path or DECISIONS_PATH
    if not os.path.exists(p):
        return []
    out: List[Dict[str, Any]] = []
    text = open(p, encoding="utf-8").read()
    dec = json.JSONDecoder()
    i = 0
    while i < len(text):
        while i < len(text) and text[i].isspace():
            i += 1
        if i >= len(text):
            break
        try:
            obj, j = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            break
        out.append(obj)
        i = j
    return out


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _summarize_decision(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract a short, comparable summary from one decision record."""
    ticker = record.get("ticker", "?")
    recorded_at = record.get("recorded_at", "?")

    # Layer-1 regimes (may be missing on minimal records)
    l1 = record.get("layer1", {})
    market = l1.get("market_agent", {}) if isinstance(l1, dict) else {}
    vol = l1.get("volatility_agent", {}) if isinstance(l1, dict) else {}
    market_regime = market.get("market_regime", "unknown")
    directional_bias = market.get("directional_bias", "unknown")
    volatility_regime = vol.get("volatility_regime", "unknown")
    iv_assessment = vol.get("iv_assessment", "")

    # Final outcome
    final = record.get("final", "unknown")
    reason = record.get("reason", "")

    # Mentor audit (optional -- some records may lack it)
    mentor = record.get("mentor_audit_v1") or {}
    mentor_decision = mentor.get("overall_decision", "unknown")
    imperfections = mentor.get("imperfections", [])
    mentor_summary = {
        "decision": mentor_decision,
        "n_imperfections": len(imperfections),
        "imperfections": [
            {
                "component": imp.get("component"),
                "owner": imp.get("owner"),
                "severity": imp.get("severity"),
            }
            for imp in imperfections
        ],
    }

    # Execution / outcome (optional)
    execution = record.get("execution", {})
    outcome = record.get("outcome", {})
    outcome_summary = {
        "execution_status": execution.get("status", "unknown"),
        "pnl_unrealized": outcome.get("pnl_unrealized"),
        "pct_of_max_profit": outcome.get("pct_of_max_profit"),
    }

    return {
        "ticker": ticker,
        "recorded_at": recorded_at,
        "situation": {
            "market_regime": market_regime,
            "directional_bias": directional_bias,
            "volatility_regime": volatility_regime,
            "iv_assessment": iv_assessment,
        },
        "decision": final,
        "decision_reason": reason,
        "mentor_audit": mentor_summary,
        "outcome": outcome_summary,
    }


# ---------------------------------------------------------------------------
# Main retrieval
# ---------------------------------------------------------------------------

def retrieve_context(
    ticker: str | None = None,
    market_regime: str | None = None,
    volatility_regime: str | None = None,
    max_results: int = 3,
    decisions_path: str | None = None,
    imperfections_path: str | None = None,
) -> List[Dict[str, Any]]:
    """Search past decisions for matching / similar situation tags.

    Scoring (higher = better match):
      - exact ticker match:                                                     +3
      - exact market_regime match:                                              +1
      - exact volatility_regime match:                                          +1

    Records that match at least one *provided* tag are included.  Results are
    sorted by score descending and truncated to ``max_results``.

    Also searches ``imperfections_log.jsonl`` for related per-agent weakness
    observations and attaches them under the ``past_observations`` key on each
    summary.

    Returns a list of summary dicts.  When no decisions exist or no tags match,
    returns an empty list and logs the result plainly -- this is expected with
    a handful of historical decisions and is NOT padded to look useful.
    """
    traces = _load_decision_traces(decisions_path)
    if not traces:
        logger.info(
            "retrieve_context: no decision records found at %s",
            decisions_path or DECISIONS_PATH,
        )
        return []

    scored: List[tuple[int, Dict[str, Any]]] = []
    for record in traces:
        summary = _summarize_decision(record)
        score = 0
        if ticker and record.get("ticker") == ticker:
            score += 3
        if (market_regime
                and summary["situation"]["market_regime"] == market_regime):
            score += 1
        if (volatility_regime
                and summary["situation"]["volatility_regime"] == volatility_regime):
            score += 1
        if score > 0:
            scored.append((score, summary))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [s for _, s in scored[:max_results]]

    # Enrich with related imperfection-log observations (per-agent).
    if results:
        _enrich_with_observations(results, imperfections_path)

    if not results:
        logger.info(
            "retrieve_context: %d records searched, 0 matches "
            "(ticker=%s, market_regime=%s, volatility_regime=%s) "
            "-- returning empty (honest: too few observations to be useful)",
            len(traces), ticker, market_regime, volatility_regime,
        )
    else:
        logger.info(
            "retrieve_context: %d/%d records matched "
            "(ticker=%s, market_regime=%s, volatility_regime=%s)",
            len(results), len(traces), ticker, market_regime, volatility_regime,
        )

    return results


def _enrich_with_observations(
    summaries: List[Dict[str, Any]],
    imperfections_path: str | None = None,
) -> None:
    """Attach relevant imperfection-log observations to each summary.

    Matches on agent name: if a decision record involved agent X and the
    imperfection log has observations for agent X, those observations are
    appended.  This is a best-effort enrichment -- empty lists are fine.
    """
    logs = imperfection_log.load(imperfections_path if imperfections_path else None)
    if not logs:
        return

    # Index observations by agent for quick lookup.
    by_agent: Dict[str, List[str]] = {}
    for entry in logs:
        agent = entry.get("agent", "")
        if not agent:
            continue
        note = entry.get("weak_area", "") or entry.get("note", "")
        if note:
            by_agent.setdefault(agent, []).append(note)

    for summary in summaries:
        # The decision record involved all 7 agents; we highlight observations
        # for the strategist (decision-maker) and whoever the Mentor flagged.
        relevant: List[str] = []
        # Strategist observations are always relevant (it makes the call).
        relevant.extend(by_agent.get("strategist", []))
        # Mentor observations.
        relevant.extend(by_agent.get("mentor", []))
        # Any owners flagged in the Mentor audit.
        for imp in summary.get("mentor_audit", {}).get("imperfections", []):
            owner = imp.get("owner", "")
            if owner in by_agent:
                relevant.extend(by_agent[owner])
        summary["past_observations"] = relevant


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_for_prompt(summaries: List[Dict[str, Any]]) -> str:
    """Format retrieved summaries as a short, readable block for injection
    into an agent's prompt.

    Returns an empty string when there are no summaries (caller should omit
    the section entirely rather than inject an empty/noise block).
    """
    if not summaries:
        return ""
    lines: List[str] = [
        "PAST SIMILAR SITUATIONS (retrieved from decision history):"
    ]
    for s in summaries:
        lines.append(
            f"  - {s['recorded_at']} | {s['ticker']} | "
            f"market={s['situation']['market_regime']} | "
            f"vol={s['situation']['volatility_regime']} | "
            f"decision={s['decision']}"
        )
        if s.get("mentor_audit", {}).get("decision") not in ("unknown", None):
            n_imp = s["mentor_audit"]["n_imperfections"]
            lines.append(
                f"      Mentor: {s['mentor_audit']['decision']} "
                f"({n_imp} imperfection{'s' if n_imp != 1 else ''})"
            )
        if s.get("decision_reason"):
            lines.append(f"      Reason: {s['decision_reason']}")
    lines.append(
        "Note: these are mechanism demos with n=1-5 historical samples; "
        "use them as context, NOT as statistically validated precedents."
    )
    return "\n".join(lines)


def format_for_agent(
    agent_name: str,
    summaries: List[Dict[str, Any]],
) -> str:
    """Format retrieved summaries filtered to the domain of *agent_name*.

    Each agent sees only the fields relevant to its ownership area:
      - market_agent:      market regime, directional bias, outcome
      - volatility_agent:  volatility regime, IV assessment, outcome
      - options_agent:     structure decisions, Mentor flags on contracts
      - strategist:        full summaries (synthesizer sees everything)
      - (other):           falls back to generic ``format_for_prompt``

    Returns an empty string when there are no summaries.
    """
    if not summaries:
        return ""

    formatters = {
        "market_agent": _fmt_market,
        "volatility_agent": _fmt_volatility,
        "options_agent": _fmt_options,
        "strategist": format_for_prompt,  # full view
    }
    fn = formatters.get(agent_name, format_for_prompt)
    return fn(summaries)


def _fmt_market(summaries: List[Dict[str, Any]]) -> str:
    lines: List[str] = [
        "PAST SIMILAR SITUATIONS (market regime history):"
    ]
    for s in summaries:
        lines.append(
            f"  - {s['recorded_at']} | {s['ticker']} | "
            f"regime={s['situation']['market_regime']} | "
            f"bias={s['situation']['directional_bias']} | "
            f"decision={s['decision']}"
        )
        if s.get("decision_reason"):
            lines.append(f"      Reason: {s['decision_reason']}")
    lines.append(_CAVEAT)
    return "\n".join(lines)


def _fmt_volatility(summaries: List[Dict[str, Any]]) -> str:
    lines: List[str] = [
        "PAST SIMILAR SITUATIONS (volatility regime history):"
    ]
    for s in summaries:
        lines.append(
            f"  - {s['recorded_at']} | {s['ticker']} | "
            f"vol_regime={s['situation']['volatility_regime']} | "
            f"iv={s['situation']['iv_assessment'][:60] if s['situation']['iv_assessment'] else 'n/a'} | "
            f"decision={s['decision']}"
        )
        # Surface Mentor flags relevant to volatility analysis.
        for imp in s.get("mentor_audit", {}).get("imperfections", []):
            if imp.get("owner") == "volatility_agent":
                lines.append(
                    f"      Mentor flag [{imp.get('severity')}]: {imp.get('component')}"
                )
        if s.get("decision_reason"):
            lines.append(f"      Reason: {s['decision_reason']}")
    lines.append(_CAVEAT)
    return "\n".join(lines)


def _fmt_options(summaries: List[Dict[str, Any]]) -> str:
    lines: List[str] = [
        "PAST SIMILAR SITUATIONS (options structure history):"
    ]
    for s in summaries:
        lines.append(
            f"  - {s['recorded_at']} | {s['ticker']} | "
            f"market={s['situation']['market_regime']} | "
            f"vol={s['situation']['volatility_regime']} | "
            f"decision={s['decision']}"
        )
        # Surface Mentor flags relevant to options/contract selection.
        for imp in s.get("mentor_audit", {}).get("imperfections", []):
            if imp.get("owner") in ("options_agent", "strategist"):
                lines.append(
                    f"      Mentor flag [{imp.get('severity')}]: {imp.get('component')}"
                )
        if s.get("decision_reason"):
            lines.append(f"      Reason: {s['decision_reason']}")
    lines.append(_CAVEAT)
    return "\n".join(lines)


_CAVEAT = (
    "Note: these are mechanism demos with n=1-5 historical samples; "
    "use them as context, NOT as statistically validated precedents."
)


# ---------------------------------------------------------------------------
# Convenience: one-call retrieval + formatting for a named agent
# ---------------------------------------------------------------------------

def retrieve_for_agent(
    agent_name: str,
    ticker: str | None = None,
    market_regime: str | None = None,
    volatility_regime: str | None = None,
    max_results: int = 3,
    decisions_path: str | None = None,
    imperfections_path: str | None = None,
) -> str:
    """Retrieve past decisions and format them for *agent_name*'s prompt.

    Returns an empty string when no matches are found (caller should simply
    omit the block from the prompt).  Never raises -- logs errors and returns
    empty on failure so the agent runs exactly as before.
    """
    try:
        summaries = retrieve_context(
            ticker=ticker,
            market_regime=market_regime,
            volatility_regime=volatility_regime,
            max_results=max_results,
            decisions_path=decisions_path,
            imperfections_path=imperfections_path,
        )
        return format_for_agent(agent_name, summaries)
    except Exception:
        logger.exception(
            "retrieve_for_agent(%s): retrieval failed, returning empty "
            "(agent will run without past context)",
            agent_name,
        )
        return ""
