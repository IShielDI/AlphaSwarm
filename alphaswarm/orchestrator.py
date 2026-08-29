"""Orchestrator -- one decision cycle, end to end.

Flow (Agent Rules Section 3.3, TRD Section 4):
  Layer 1 (market, volatility, options, portfolio)
    -> Strategist proposal
    -> Mentor audit
    -> [at most ONE correction round: re-invoke only flagged owners,
        respecting invalidate_downstream]
    -> Mentor re-audit
    -> APPROVE ? Risk Engine (deterministic, no-LLM)
    -> PASS ? Execution Service (atomic mleg order, Alpaca paper)
    -> Position Monitor (separate scheduled process)

HARD CAP: exactly ONE revision round. If the re-audit is not APPROVE,
the cycle ends NO_TRADE. No open-ended looping, by design.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Tuple

from . import config
from .agents.llm_client import AgentSchemaError, LLMError
from .agents.market_agent import MarketAgent
from .agents.mentor import Mentor
from .agents.options_agent import OptionsAgent
from .agents.portfolio_agent import PortfolioAgent
from .agents.strategist import Strategist
from .agents.volatility_agent import VolatilityAgent
from .data.alpaca_client import AlpacaClient
from .decision_store import record_cycle
from .engine.execution_service import ExecutionService
from .engine.risk_engine import RiskEngine, SpreadTrade

logger = logging.getLogger(__name__)

# Ownership routing map (Agent Rules Section 1 table).
# owner -> (layer1 order index, downstream agents that consume its output).
_OWNERSHIP = {
    "market_agent": (0, ["options_agent", "strategist"]),
    "volatility_agent": (1, ["options_agent", "strategist"]),
    "options_agent": (2, ["strategist"]),
    "portfolio_agent": (3, ["strategist"]),
    "strategist": (4, []),
    "none": (None, []),
}
_LAYER_ORDER = ["market_agent", "volatility_agent", "options_agent", "portfolio_agent"]


class Orchestrator:
    def __init__(self, paper: bool = True):
        self.market = MarketAgent()
        self.vol = VolatilityAgent()
        self.options = OptionsAgent()
        self.portfolio = PortfolioAgent()
        self.strategist = Strategist()
        self.mentor = Mentor()
        self.risk_engine = RiskEngine()
        self.execution = ExecutionService()
        self.alpaca = AlpacaClient()

    # ------------------------------------------------------------------
    # Layer 1
    # ------------------------------------------------------------------
    def _run_layer1(self, ticker: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        market = self.market.analyze(ticker)
        vol = self.vol.analyze(ticker)
        options = self.options.analyze(
            ticker,
            context={
                "market_regime": market["market_regime"],
                "directional_bias": market["directional_bias"],
                "volatility_regime": vol["volatility_regime"],
                "iv_assessment": vol["iv_assessment"],
            },
        )
        portfolio = self.portfolio.analyze(
            ticker,
            context={
                "proposed_structure": options["candidate_structures"],
                "contract_candidates": options["contract_candidates"],
            },
        )
        return [market, vol, options, portfolio], {}

    @staticmethod
    def _options_context(l1: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "market_regime": l1[0]["market_regime"],
            "directional_bias": l1[0]["directional_bias"],
            "volatility_regime": l1[1]["volatility_regime"],
            "iv_assessment": l1[1]["iv_assessment"],
        }

    @staticmethod
    def _portfolio_context(l1: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "proposed_structure": l1[2]["candidate_structures"],
            "contract_candidates": l1[2]["contract_candidates"],
        }

    # ------------------------------------------------------------------
    # Correction round (exactly one)
    # ------------------------------------------------------------------
    def _correction_round(
        self, ticker: str, l1: List[Dict[str, Any]], proposal: Dict[str, Any],
        audit: Dict[str, Any], trace: Dict[str, Any],
    ) -> Tuple[List[Dict[str, Any]], Any]:
        """Re-invoke ONLY the agents the Mentor flagged, then re-synthesize.

        invalidate_downstream semantics: a corrected Layer-1 output forces
        re-execution of every downstream agent that consumed it. A corrected
        Layer-1 agent itself is re-run with its original inputs (the flaw was
        in its analysis, not its data).
        """
        owners = {
            imp.get("owner")
            for imp in audit.get("imperfections", [])
            if imp.get("owner") in _OWNERSHIP
        }
        trace["correction_flagged_owners"] = sorted(owners)
        logger.info("correction round: flagged owners=%s", sorted(owners))

        rerun: Dict[str, bool] = {name: False for name in _LAYER_ORDER}
        for owner in owners:
            idx, downstream = _OWNERSHIP[owner]
            if idx is None:
                continue
            if idx < 4:
                rerun[_LAYER_ORDER[idx]] = True
            for d in downstream:
                if d in rerun:
                    rerun[d] = True

        # Re-run corrected Layer-1 agents in dependency order.
        if rerun["market_agent"]:
            l1[0] = self.market.analyze(ticker)
        if rerun["volatility_agent"]:
            l1[1] = self.vol.analyze(ticker)
        if rerun["options_agent"]:
            l1[2] = self.options.analyze(ticker, context=self._options_context(l1))
        if rerun["portfolio_agent"]:
            l1[3] = self.portfolio.analyze(ticker, context=self._portfolio_context(l1))
        trace["correction_rerun"] = [k for k, v in rerun.items() if v]

        # The strategist always re-synthesizes with Mentor feedback included.
        new_proposal = self.strategist.synthesize(
            ticker, l1[0], l1[1], l1[2], l1[3],
            mentor_feedback=audit,
        )
        return l1, new_proposal

    # ------------------------------------------------------------------
    # Proposal -> trade + risk + execution
    # ------------------------------------------------------------------
    @staticmethod
    def _to_trade(proposal: Dict[str, Any], contracts: int = 1) -> SpreadTrade:
        c = proposal["contract"]
        return SpreadTrade(
            underlying=proposal["underlying"],
            structure=proposal["selected_structure"],
            expiration=c["expiration"],
            short_strike=float(c["short_leg"]["strike"]),
            long_strike=float(c["long_leg"]["strike"]),
            credit_received=float(c["estimated_credit"]),
            contracts=contracts,
            short_symbol=c["short_leg"]["symbol"],
            long_symbol=c["long_leg"]["symbol"],
        )

    def _execute(self, proposal: Dict[str, Any], trace: Dict[str, Any]) -> Dict[str, Any]:
        trade = self._to_trade(proposal)
        account = self.alpaca.get_account_summary()
        equity = float(account.get("equity", 0) or 0)
        risk = self.risk_engine.check(trade, equity)
        trace["risk_engine"] = {
            "verdict": risk.summary(),
            "checks": [vars(c) for c in risk.checks],
            "equity": equity,
        }
        if not risk.passed:
            logger.warning("risk engine FAIL: %s", risk.failed_checks)
            return {"status": "RISK_FAIL", "detail": risk.failed_checks}

        builder = (
            self.execution.build_bull_put_spread
            if trade.structure == "bull_put_spread"
            else self.execution.build_bear_call_spread
        )
        legs = builder(trade.short_symbol, trade.long_symbol)
        # Net credit limit: sell for at least the estimated credit.
        limit = round(trade.credit_received, 2)
        order = self.execution.submit_spread(
            legs,
            qty=trade.contracts,
            order_type="limit",
            limit_price=limit,
            client_order_id=f"alphaswarm-{trade.underlying}-{int(time.time())}",
        )
        result = {
            "status": "SUBMITTED",
            "order_id": str(getattr(order, "id", order)),
            "status_raw": str(getattr(order, "status", "")),
            "qty": trade.contracts,
            "limit_price": limit,
            "legs": [trade.short_symbol, trade.long_symbol],
        }
        trace["execution"] = result
        logger.info("order submitted: %s", result)
        return result

    # ------------------------------------------------------------------
    # The cycle
    # ------------------------------------------------------------------
    def run_cycle(self, ticker: str, execute: bool = True) -> Dict[str, Any]:
        trace: Dict[str, Any] = {"ticker": ticker, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}

        l1, _ = self._run_layer1(ticker)
        trace["layer1"] = dict(zip(_LAYER_ORDER, l1))

        proposal = self.strategist.synthesize(ticker, l1[0], l1[1], l1[2], l1[3])
        if proposal == "NO_TRADE":
            trace["final"] = "NO_TRADE"
            trace["reason"] = "strategist returned NO_TRADE on first synthesis"
            record_cycle(trace)
            return trace
        trace["proposal_v1"] = proposal

        audit = self.mentor.audit(ticker, proposal, l1[0], l1[1], l1[2], l1[3])
        trace["mentor_audit_v1"] = audit
        decision = audit["overall_decision"]

        if decision != "APPROVE":
            # Exactly ONE correction round (Agent Rules 3.3).
            if decision == "REVISE":
                l1, proposal2 = self._correction_round(ticker, l1, proposal, audit, trace)
                if proposal2 == "NO_TRADE":
                    trace["final"] = "NO_TRADE"
                    trace["reason"] = "strategist returned NO_TRADE during correction round"
                    record_cycle(trace)
                    return trace
                trace["proposal_v2"] = proposal2
                audit2 = self.mentor.audit(ticker, proposal2, l1[0], l1[1], l1[2], l1[3])
                trace["mentor_audit_v2"] = audit2
                decision = audit2["overall_decision"]
                audit, proposal = audit2, proposal2
            # REJECT / WAIT or failed re-audit: full stop. No second round.
            if decision != "APPROVE":
                trace["final"] = "NO_TRADE"
                trace["reason"] = f"mentor decision {decision} (one-revision cap reached)"
                record_cycle(trace)
                return trace

        trace["final"] = "APPROVED"
        if not execute:
            trace["execution"] = {"status": "SKIPPED (dry run)"}
            record_cycle(trace)
            return trace

        try:
            trace["execution"] = self._execute(proposal, trace)
        except Exception as e:  # execution must never crash the trace
            logger.exception("execution error")
            trace["execution"] = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"}
        record_cycle(trace)
        return trace
