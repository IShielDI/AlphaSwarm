"""Tests for alphaswarm.improve.retrieval -- past-decision tag matching.

Uses temporary JSONL fixtures (no live data, no LLM calls).
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Dict, List

import pytest

from alphaswarm.improve import retrieval


# ---------------------------------------------------------------------------
# Fixtures: tiny JSONL decision log + imperfection log
# ---------------------------------------------------------------------------

_DECISION_AAPL = {
    "ticker": "AAPL",
    "started_at": "2026-08-29T11:42:28+0530",
    "layer1": {
        "market_agent": {
            "market_regime": "range_bound",
            "directional_bias": "neutral",
            "confidence": 0.6,
            "supporting_evidence": ["sma_20 close to sma_50"],
            "contradictory_evidence": [],
            "risk_factors": ["spot is 0.0"],
        },
        "volatility_agent": {
            "volatility_regime": "elevated",
            "iv_assessment": "expensive relative to realized vol; IV ~36% vs realized 18.9%",
            "realized_vol_assessment": "low and stable",
            "term_structure_assessment": "backwardation",
            "confidence": 0.85,
            "evidence": [],
            "warnings": [],
        },
    },
    "final": "NO_TRADE",
    "reason": "strategist returned NO_TRADE on first synthesis",
    "recorded_at": "2026-08-29T11:46:00+0530",
}

_DECISION_NVDA = {
    "ticker": "NVDA",
    "started_at": "2026-08-29T11:47:33+0530",
    "layer1": {
        "market_agent": {
            "market_regime": "trending_up",
            "directional_bias": "bullish",
            "confidence": 0.78,
            "supporting_evidence": ["spot above sma_20 and sma_50"],
            "contradictory_evidence": [],
            "risk_factors": [],
        },
        "volatility_agent": {
            "volatility_regime": "elevated",
            "iv_assessment": "expensive relative to longer-dated IV",
            "realized_vol_assessment": "elevated and rising",
            "term_structure_assessment": "backwardation",
            "confidence": 0.85,
            "evidence": [],
            "warnings": [],
        },
    },
    "mentor_audit_v1": {
        "overall_decision": "REVISE",
        "imperfections": [
            {
                "component": "contract_symbol",
                "owner": "options_agent",
                "severity": "high",
                "reason": "Mismatched expiration",
            },
            {
                "component": "ITM_mischaracterization",
                "owner": "strategist",
                "severity": "medium",
                "reason": "Wrong moneyness",
            },
        ],
    },
    "final": "NO_TRADE",
    "reason": "strategist returned NO_TRADE during correction round",
    "recorded_at": "2026-08-29T11:49:43+0530",
}

_DECISION_AMD = {
    "ticker": "AMD",
    "started_at": "2026-08-29T11:53:17+0530",
    "layer1": {
        "market_agent": {
            "market_regime": "trending_down",
            "directional_bias": "bearish",
            "confidence": 0.65,
            "supporting_evidence": [],
            "contradictory_evidence": [],
            "risk_factors": [],
        },
        "volatility_agent": {
            "volatility_regime": "elevated",
            "iv_assessment": "expensive relative to recent realized vol",
            "realized_vol_assessment": "elevated but declining",
            "term_structure_assessment": "mixed",
            "confidence": 0.8,
            "evidence": [],
            "warnings": [],
        },
    },
    "final": "NO_TRADE",
    "reason": "strategist returned NO_TRADE on first synthesis",
    "recorded_at": "2026-08-29T11:55:00+0530",
}

_DECISION_MSFT = {
    "ticker": "MSFT",
    "started_at": "2026-08-29T11:49:43+0530",
    "layer1": {
        "market_agent": {
            "market_regime": "trending_up",
            "directional_bias": "bullish",
            "confidence": 0.85,
            "supporting_evidence": [],
            "contradictory_evidence": [],
            "risk_factors": [],
        },
        "volatility_agent": {
            "volatility_regime": "elevated",
            "iv_assessment": "expensive",
            "realized_vol_assessment": "declining",
            "term_structure_assessment": "slight backwardation then contango",
            "confidence": 0.9,
            "evidence": [],
            "warnings": [],
        },
    },
    "final": "NO_TRADE",
    "reason": "strategist returned NO_TRADE on first synthesis",
    "recorded_at": "2026-08-29T11:52:03+0530",
}

_IMPERFECTION_ENTRIES = [
    {
        "recorded_at": "2026-08-29T07:09:54+00:00",
        "agent": "strategist",
        "strength_area": "faithful synthesis",
        "weak_area": "NO_TRADE over-caution when Portfolio flags any conflict",
        "source": "days1-3_manual_observation",
        "note": "single-observation anecdote, NOT a validated finding",
    },
    {
        "recorded_at": "2026-08-29T07:09:54+00:00",
        "agent": "options_agent",
        "strength_area": "used only real Alpaca quotes",
        "weak_area": "expiry selection picked 2-DTE contracts under steep backwardation",
        "source": "days1-3_manual_observation",
        "note": "single-observation anecdote, NOT a validated finding",
    },
    {
        "recorded_at": "2026-08-29T07:09:54+00:00",
        "agent": "volatility_agent",
        "strength_area": "clear IV-vs-realized-vol framing",
        "weak_area": "surfaced data anomaly as warning instead of halting",
        "source": "days1-3_manual_observation",
        "note": "single-observation anecdote, NOT a validated finding",
    },
]


def _write_decisions(path: str, records: List[Dict[str, Any]]) -> None:
    """Write multi-object pretty-printed JSONL (matches real format)."""
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, indent=2) + "\n")


def _write_imperfections(path: str, entries: List[Dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


@pytest.fixture
def decisions_file(tmp_path):
    p = str(tmp_path / "decisions.jsonl")
    _write_decisions(p, [_DECISION_AAPL, _DECISION_NVDA, _DECISION_AMD, _DECISION_MSFT])
    return p


@pytest.fixture
def empty_decisions_file(tmp_path):
    p = str(tmp_path / "decisions_empty.jsonl")
    return p  # file doesn't exist


@pytest.fixture
def imperfections_file(tmp_path):
    p = str(tmp_path / "imperfections_log.jsonl")
    _write_imperfections(p, _IMPERFECTION_ENTRIES)
    return p


@pytest.fixture
def empty_imperfections_file(tmp_path):
    p = str(tmp_path / "imperfections_empty.jsonl")
    return p  # file doesn't exist


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRetrieveContext:
    """Core retrieve_context() function."""

    def test_empty_log_returns_empty(self, empty_decisions_file):
        """No decisions file -> empty results, logged plainly."""
        result = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=empty_decisions_file,
        )
        assert result == []

    def test_exact_ticker_match(self, decisions_file, empty_imperfections_file):
        """Ticker match scores highest (+3)."""
        result = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert len(result) >= 1
        assert result[0]["ticker"] == "AAPL"

    def test_regime_match(self, decisions_file, empty_imperfections_file):
        """market_regime and volatility_regime matches included."""
        result = retrieval.retrieve_context(
            market_regime="trending_up",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        # NVDA + MSFT both have trending_up
        tickers = {r["ticker"] for r in result}
        assert "NVDA" in tickers
        assert "MSFT" in tickers

    def test_volatility_regime_match(self, decisions_file, empty_imperfections_file):
        """All four records have elevated vol, so all match."""
        result = retrieval.retrieve_context(
            volatility_regime="elevated",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
            max_results=10,
        )
        assert len(result) == 4

    def test_no_match_returns_empty(self, decisions_file, empty_imperfections_file):
        """Tags that don't match anything -> empty, honest log."""
        result = retrieval.retrieve_context(
            ticker="TSLA",
            market_regime="choppy",
            volatility_regime="low",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert result == []

    def test_max_results_honored(self, decisions_file, empty_imperfections_file):
        """Cap at max_results."""
        result = retrieval.retrieve_context(
            volatility_regime="elevated",
            max_results=2,
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert len(result) == 2

    def test_combined_score_ordering(self, decisions_file, empty_imperfections_file):
        """Ticker + regime match scores higher than regime-only match."""
        result = retrieval.retrieve_context(
            ticker="NVDA",
            market_regime="trending_up",
            volatility_regime="elevated",
            max_results=3,
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        # NVDA matches all three tags (score=5), should be first
        assert result[0]["ticker"] == "NVDA"


class TestFormatForPrompt:
    """Generic format_for_prompt()."""

    def test_empty_returns_empty_string(self):
        assert retrieval.format_for_prompt([]) == ""

    def test_content_has_header_and_caveat(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_prompt(summaries)
        assert "PAST SIMILAR SITUATIONS" in text
        assert "mechanism demos" in text
        assert "NOT as statistically validated" in text

    def test_includes_decision_and_reason(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_prompt(summaries)
        assert "NO_TRADE" in text
        assert "AAPL" in text

    def test_mentor_info_included_when_present(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            ticker="NVDA",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_prompt(summaries)
        assert "Mentor: REVISE" in text
        assert "2 imperfections" in text


class TestFormatForAgent:
    """Agent-specific format_for_agent()."""

    def test_market_agent_format(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_agent("market_agent", summaries)
        assert "market regime history" in text
        assert "regime=range_bound" in text
        assert "bias=neutral" in text

    def test_volatility_agent_format(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            volatility_regime="elevated",
            max_results=1,
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_agent("volatility_agent", summaries)
        assert "volatility regime history" in text
        assert "vol_regime=elevated" in text

    def test_options_agent_format_with_mentor_flags(self, decisions_file, empty_imperfections_file):
        """Options agent format surfaces Mentor flags for options_agent and strategist."""
        summaries = retrieval.retrieve_context(
            ticker="NVDA",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        text = retrieval.format_for_agent("options_agent", summaries)
        assert "options structure history" in text
        # NVDA has Mentor flags for options_agent and strategist
        assert "Mentor flag [high]: contract_symbol" in text
        assert "Mentor flag [medium]: ITM_mischaracterization" in text

    def test_strategist_gets_full_view(self, decisions_file, empty_imperfections_file):
        """Strategist format is the same as the generic format_for_prompt."""
        summaries = retrieval.retrieve_context(
            ticker="NVDA",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        generic = retrieval.format_for_prompt(summaries)
        agent = retrieval.format_for_agent("strategist", summaries)
        assert generic == agent

    def test_unknown_agent_falls_back_to_generic(self, decisions_file, empty_imperfections_file):
        summaries = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        generic = retrieval.format_for_prompt(summaries)
        fallback = retrieval.format_for_agent("portfolio_agent", summaries)
        assert generic == fallback

    def test_empty_summaries_returns_empty(self):
        assert retrieval.format_for_agent("market_agent", []) == ""
        assert retrieval.format_for_agent("volatility_agent", []) == ""
        assert retrieval.format_for_agent("options_agent", []) == ""
        assert retrieval.format_for_agent("strategist", []) == ""


class TestImperfectionEnrichment:
    """Imperfection log observations attached to summaries."""

    def test_enrichment_attaches_observations(self, decisions_file, imperfections_file):
        """past_observations key present with relevant entries."""
        result = retrieval.retrieve_context(
            ticker="NVDA",
            decisions_path=decisions_file,
            imperfections_path=imperfections_file,
        )
        assert len(result) >= 1
        obs = result[0].get("past_observations", [])
        # NVDA mentor flagged options_agent and strategist
        # So we expect strategist + mentor + options_agent observations
        assert any("NO_TRADE over-caution" in o for o in obs)  # strategist
        assert any("expiry selection" in o for o in obs)  # options_agent

    def test_enrichment_no_crash_on_empty_imperfection_log(
        self, decisions_file, empty_imperfections_file
    ):
        """Works fine when imperfection log doesn't exist."""
        result = retrieval.retrieve_context(
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert len(result) >= 1
        # past_observations should still be present (even if empty)
        obs = result[0].get("past_observations", [])
        assert isinstance(obs, list)


class TestRetrieveForAgent:
    """Convenience function: one-call retrieval + formatting."""

    def test_returns_string(self, decisions_file, empty_imperfections_file):
        text = retrieval.retrieve_for_agent(
            "market_agent",
            ticker="AAPL",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert isinstance(text, str)
        assert "AAPL" in text

    def test_returns_empty_on_no_match(self, decisions_file, empty_imperfections_file):
        text = retrieval.retrieve_for_agent(
            "market_agent",
            ticker="TSLA",
            market_regime="choppy",
            decisions_path=decisions_file,
            imperfections_path=empty_imperfections_file,
        )
        assert text == ""

    def test_returns_empty_on_missing_file(self, empty_decisions_file):
        """Missing decisions file -> empty string, no crash."""
        text = retrieval.retrieve_for_agent(
            "volatility_agent",
            ticker="AAPL",
            decisions_path=empty_decisions_file,
        )
        assert text == ""

    def test_never_raises(self, tmp_path):
        """Even if the path is garbage, returns empty string."""
        text = retrieval.retrieve_for_agent(
            "strategist",
            ticker="AAPL",
            decisions_path=str(tmp_path / "nonexistent.jsonl"),
        )
        assert text == ""


class TestSummarizeDecision:
    """Internal _summarize_decision()."""

    def test_summary_fields_present(self):
        summary = retrieval._summarize_decision(_DECISION_AAPL)
        assert summary["ticker"] == "AAPL"
        assert summary["situation"]["market_regime"] == "range_bound"
        assert summary["situation"]["volatility_regime"] == "elevated"
        assert summary["decision"] == "NO_TRADE"
        assert summary["decision_reason"] != ""

    def test_mentor_audit_extracted(self):
        summary = retrieval._summarize_decision(_DECISION_NVDA)
        assert summary["mentor_audit"]["decision"] == "REVISE"
        assert summary["mentor_audit"]["n_imperfections"] == 2


class TestTypoBugRegression:
    """Regression test: the typo 'imperfectments_path' should be fixed."""

    def test_enrich_does_not_crash(self, imperfections_file):
        """_enrich_with_observations must not raise NameError."""
        summaries = [retrieval._summarize_decision(_DECISION_NVDA)]
        # This would crash pre-fix with: NameError: name 'imperfectments_path'
        retrieval._enrich_with_observations(summaries, imperfections_path=imperfections_file)
        assert "past_observations" in summaries[0]
