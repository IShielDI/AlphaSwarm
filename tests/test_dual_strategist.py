"""Tests for Dual Strategist parallel synthesis and arbitration feature."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from alphaswarm import config
from alphaswarm.agents.strategist import (
    ConservativeStrategist,
    Strategist,
    arbitrate_proposals,
)
from alphaswarm.orchestrator import Orchestrator


_MOCK_PROPOSAL_BULL_PUT = {
    "underlying": "AAPL",
    "market_thesis": "Bullish trend supported by SMA20 > SMA50.",
    "volatility_thesis": "Elevated IV relative to realized vol.",
    "selected_structure": "bull_put_spread",
    "contract": {
        "short_leg": {"symbol": "AAPL260918P00150000", "strike": 150.0},
        "long_leg": {"symbol": "AAPL260918P00145000", "strike": 145.0},
        "expiration": "260918",
        "estimated_credit": 1.20,
        "max_loss_per_contract": 380.0,
    },
    "rationale": "Collect credit in elevated vol environment.",
    "alternative_structures_considered": ["bear_call_spread"],
    "entry_conditions": ["Spot > 152.0"],
    "exit_conditions": ["Take profit at 50% max profit"],
    "invalidation_conditions": ["Spot < 148.0"],
    "portfolio_impact": "Diversifies portfolio with limited risk.",
    "max_loss": 380.0,
    "key_risks": ["Directional pullback below 150"],
    "confidence": 0.85,
    "reasons_not_to_trade": ["Short DTE gamma risk"],
}

_MOCK_PROPOSAL_BEAR_CALL = {
    "underlying": "AAPL",
    "market_thesis": "Bearish resistance near high.",
    "volatility_thesis": "Elevated IV.",
    "selected_structure": "bear_call_spread",
    "contract": {
        "short_leg": {"symbol": "AAPL260918C00160000", "strike": 160.0},
        "long_leg": {"symbol": "AAPL260918C00165000", "strike": 165.0},
        "expiration": "260918",
        "estimated_credit": 1.10,
        "max_loss_per_contract": 390.0,
    },
    "rationale": "Sell call credit spread.",
    "alternative_structures_considered": ["bull_put_spread"],
    "entry_conditions": ["Spot < 155.0"],
    "exit_conditions": ["Take profit at 50%"],
    "invalidation_conditions": ["Spot > 160.0"],
    "portfolio_impact": "Short delta exposure.",
    "max_loss": 390.0,
    "key_risks": ["Breakout above 160"],
    "confidence": 0.75,
    "reasons_not_to_trade": ["Market uptrend momentum"],
}


class TestDualStrategistArbitration:
    """Isolated unit tests for arbitrate_proposals function."""

    def test_both_no_trade(self):
        result, meta = arbitrate_proposals("NO_TRADE", "NO_TRADE")
        assert result == "NO_TRADE"
        assert meta["agreed"] is True
        assert meta["decision"] == "NO_TRADE"

    def test_both_agree_on_same_structure(self):
        p1 = dict(_MOCK_PROPOSAL_BULL_PUT)
        p2 = dict(_MOCK_PROPOSAL_BULL_PUT)
        result, meta = arbitrate_proposals(p1, p2)
        assert result == p1
        assert meta["agreed"] is True
        assert meta["structure"] == "bull_put_spread"

    def test_disagree_primary_trade_secondary_notrade(self):
        p1 = dict(_MOCK_PROPOSAL_BULL_PUT)
        result, meta = arbitrate_proposals(p1, "NO_TRADE")
        assert isinstance(result, dict)
        assert meta["agreed"] is False
        assert meta["decision"] == "DISAGREEMENT_SURFACED_TO_MENTOR"
        assert "dual_strategist_arbitration" in result
        assert result["dual_strategist_arbitration"]["disagreement"] is True
        assert result["dual_strategist_arbitration"]["secondary_proposal"] == "NO_TRADE"

    def test_disagree_primary_notrade_secondary_trade(self):
        p2 = dict(_MOCK_PROPOSAL_BEAR_CALL)
        result, meta = arbitrate_proposals("NO_TRADE", p2)
        assert isinstance(result, dict)
        assert meta["agreed"] is False
        assert meta["decision"] == "DISAGREEMENT_SURFACED_TO_MENTOR"
        assert "dual_strategist_arbitration" in result
        assert result["dual_strategist_arbitration"]["disagreement"] is True
        assert result["dual_strategist_arbitration"]["primary_proposal"] == "NO_TRADE"

    def test_disagree_different_structures(self):
        p1 = dict(_MOCK_PROPOSAL_BULL_PUT)
        p2 = dict(_MOCK_PROPOSAL_BEAR_CALL)
        result, meta = arbitrate_proposals(p1, p2)
        assert isinstance(result, dict)
        assert meta["agreed"] is False
        assert meta["decision"] == "DISAGREEMENT_SURFACED_TO_MENTOR"
        assert "dual_strategist_arbitration" in result
        assert result["dual_strategist_arbitration"]["primary_proposal"]["selected_structure"] == "bull_put_spread"
        assert result["dual_strategist_arbitration"]["secondary_proposal"]["selected_structure"] == "bear_call_spread"


class TestFeatureFlagAndOrchestrator:
    """Tests feature flag default OFF and Orchestrator integration."""

    def test_feature_flag_default_is_off(self):
        assert config.ENABLE_DUAL_STRATEGIST is False

    @patch("alphaswarm.orchestrator.retrieve_for_agent", return_value="")
    @patch("alphaswarm.orchestrator.record_cycle")
    def test_default_off_path_behavior(self, mock_record, mock_retrieval):
        orc = Orchestrator()
        orc.market.analyze = MagicMock(return_value={"market_regime": "trending_up", "directional_bias": "bullish"})
        orc.vol.analyze = MagicMock(return_value={"volatility_regime": "elevated", "iv_assessment": "expensive"})
        orc.options.analyze = MagicMock(return_value={"candidate_structures": ["bull_put_spread"], "contract_candidates": []})
        orc.portfolio.analyze = MagicMock(return_value={"recommendation": "proceed"})

        orc.strategist.synthesize = MagicMock(return_value="NO_TRADE")
        orc.conservative_strategist.synthesize = MagicMock(return_value=_MOCK_PROPOSAL_BULL_PUT)

        trace = orc.run_cycle("AAPL", execute=False)

        # In default-OFF mode, secondary strategist is NOT invoked!
        orc.strategist.synthesize.assert_called_once()
        orc.conservative_strategist.synthesize.assert_not_called()
        assert trace["final"] == "NO_TRADE"
        assert "dual_strategist" not in trace

    @patch("alphaswarm.orchestrator.retrieve_for_agent", return_value="")
    @patch("alphaswarm.orchestrator.record_cycle")
    def test_dual_strategist_enabled_both_agree_notrade(self, mock_record, mock_retrieval):
        with patch.object(config, "ENABLE_DUAL_STRATEGIST", True):
            orc = Orchestrator()
            orc.market.analyze = MagicMock(return_value={"market_regime": "trending_up", "directional_bias": "bullish"})
            orc.vol.analyze = MagicMock(return_value={"volatility_regime": "elevated", "iv_assessment": "expensive"})
            orc.options.analyze = MagicMock(return_value={"candidate_structures": ["bull_put_spread"], "contract_candidates": []})
            orc.portfolio.analyze = MagicMock(return_value={"recommendation": "proceed"})

            orc.strategist.synthesize = MagicMock(return_value="NO_TRADE")
            orc.conservative_strategist.synthesize = MagicMock(return_value="NO_TRADE")
            orc.mentor.audit = MagicMock()

            trace = orc.run_cycle("AAPL", execute=False)

            assert trace["final"] == "NO_TRADE"
            assert trace["dual_strategist"]["enabled"] is True
            assert trace["dual_strategist"]["arbitration"]["agreed"] is True
            orc.mentor.audit.assert_not_called()

    @patch("alphaswarm.orchestrator.retrieve_for_agent", return_value="")
    @patch("alphaswarm.orchestrator.record_cycle")
    def test_dual_strategist_enabled_disagreement_surfaced_to_mentor(self, mock_record, mock_retrieval):
        with patch.object(config, "ENABLE_DUAL_STRATEGIST", True):
            orc = Orchestrator()
            orc.market.analyze = MagicMock(return_value={"market_regime": "trending_up", "directional_bias": "bullish"})
            orc.vol.analyze = MagicMock(return_value={"volatility_regime": "elevated", "iv_assessment": "expensive"})
            orc.options.analyze = MagicMock(return_value={"candidate_structures": ["bull_put_spread"], "contract_candidates": []})
            orc.portfolio.analyze = MagicMock(return_value={"recommendation": "proceed"})

            orc.strategist.synthesize = MagicMock(return_value=_MOCK_PROPOSAL_BULL_PUT)
            orc.conservative_strategist.synthesize = MagicMock(return_value="NO_TRADE")
            orc.mentor.audit = MagicMock(return_value={"overall_decision": "APPROVE", "imperfections": []})

            trace = orc.run_cycle("AAPL", execute=False)

            orc.mentor.audit.assert_called_once()
            audited_proposal = orc.mentor.audit.call_args[0][1]
            assert "dual_strategist_arbitration" in audited_proposal
            assert audited_proposal["dual_strategist_arbitration"]["disagreement"] is True
            assert trace["final"] == "APPROVED"
            assert trace["dual_strategist"]["arbitration"]["agreed"] is False
