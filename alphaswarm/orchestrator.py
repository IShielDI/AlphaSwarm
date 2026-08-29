"""Orchestrator -- one decision cycle, end to end.

Flow (Agent Rules Section 3.3, TRD Section 4):
  Layer 1 (market, volatility, options, portfolio)
    -> Strategist proposal
    -> Mentor audit
    -> [at most ONE correction round: re-invoke only flagged owners,
        respecting invalidate_downstream]
    -> Mentor re-audit
    -> APPROVE ? Risk Engine (deterministic, no-LLM)
    -> PASS ? [optional HUMAN_GATE soft checkpoint (Phase 5.1)] Execution
       Service (atomic mleg order, Alpaca paper)
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
from .agents.strategist import (
    ConservativeStrategist,
    Strategist,
    arbitrate_proposals,
)
from .agents.volatility_agent import VolatilityAgent
from .data.alpaca_client import AlpacaClient
from .decision_store import record_cycle
from .engine.execution_service import ExecutionService
from .engine.risk_engine import RiskEngine, SpreadTrade
from .improve.retrieval import retrieve_for_agent

logger = logging.getLogger(__name__)


class HumanRejectedError(RuntimeError):
    """Raised by the optional human approval gate (HUMAN_GATE=True) when a
    human declines an order AFTER the Risk Engine passed.

    The orchestrator treats this exactly like a Mentor REJECT for the rest of
    the cycle: no order is submitted, no retry within the same cycle, and the
    cycle records final=NO_TRADE. The Risk Engine is untouched -- the gate is
    a soft checkpoint layered after it, never a bypass or substitute.
    """


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
        self.conservative_strategist = ConservativeStrategist()
        self.mentor = Mentor()
        self.risk_engine = RiskEngine()
        self.execution = ExecutionService()
        self.alpaca = AlpacaClient()

    # ------------------------------------------------------------------
    # Layer 1
    # ------------------------------------------------------------------
    def _run_layer1(self, ticker: str) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        # Market and Volatility agents run first; at this point we only have
        # the ticker for retrieval (regime tags are their OUTPUT).
        mkt_ctx = retrieve_for_agent("market_agent", ticker=ticker)
        vol_ctx = retrieve_for_agent("volatility_agent", ticker=ticker)

        market = self.market.analyze(ticker, past_context=mkt_ctx)
        vol = self.vol.analyze(ticker, past_context=vol_ctx)

        # Now that regime tags are known, Options gets richer retrieval.
        opts_ctx = retrieve_for_agent(
            "options_agent", ticker=ticker,
            market_regime=market.get("market_regime"),
            volatility_regime=vol.get("volatility_regime"),
        )
        options = self.options.analyze(
            ticker,
            context={
                "market_regime": market["market_regime"],
                "directional_bias": market["directional_bias"],
                "volatility_regime": vol["volatility_regime"],
                "iv_assessment": vol["iv_assessment"],
            },
            past_context=opts_ctx,
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
        strat_ctx = retrieve_for_agent(
            "strategist", ticker=ticker,
            market_regime=l1[0].get("market_regime"),
            volatility_regime=l1[1].get("volatility_regime"),
        )
        if config.ENABLE_DUAL_STRATEGIST:
            p1 = self.strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3],
                mentor_feedback=audit, past_context=strat_ctx,
            )
            p2 = self.conservative_strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3],
                mentor_feedback=audit, past_context=strat_ctx,
            )
            new_proposal, arb_meta = arbitrate_proposals(p1, p2)
            trace["correction_dual_strategist"] = {
                "primary_proposal": p1,
                "secondary_proposal": p2,
                "arbitration": arb_meta,
            }
        else:
            new_proposal = self.strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3],
                mentor_feedback=audit,
                past_context=strat_ctx,
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

    def _human_gate(self, proposal: Dict[str, Any], trace: Dict[str, Any]) -> bool:
        """Optional soft checkpoint AFTER the Risk Engine passes (Phase 5.1).

        Prints a decision summary and blocks on a y/n prompt. Returns True to
        proceed to the Execution Service (same as the no-gate path), or False
        to abort this cycle exactly like a Mentor REJECT (no order, no retry
        within this cycle). Records the human_gate decision in `trace`.
        """
        contract = proposal.get("contract") or {}
        audit = trace.get("mentor_audit_v2") or trace.get("mentor_audit_v1") or {}
        imperfections = audit.get("imperfections") or []
        print("\n" + "=" * 64)
        print("HUMAN APPROVAL GATE  --  Risk Engine PASSED")
        print("=" * 64)
        print(f"Underlying           : {proposal.get('underlying')}")
        print(f"Selected structure   : {proposal.get('selected_structure')}")
        print("Contract             : "
              f"short {contract.get('short_leg', {}).get('symbol')} / "
              f"long {contract.get('long_leg', {}).get('symbol')}  "
              f"(exp {contract.get('expiration')})")
        print(f"Entry conditions     : {proposal.get('entry_conditions')}")
        print(f"Exit conditions      : {proposal.get('exit_conditions')}")
        print(f"Max loss             : ${proposal.get('max_loss')}")
        print(f"Mentor decision      : {audit.get('overall_decision')}")
        if imperfections:
            print("Mentor imperfections (last audit pass):")
            for imp in imperfections:
                print(f"  - [{imp.get('severity')}] {imp.get('component')} "
                      f"(owner={imp.get('owner')}): {imp.get('reason')}")
        else:
            print("Mentor imperfections (last audit pass): none")
        while True:
            answer = input("Submit this order? (y/n): ").strip().lower()
            if answer in ("y", "n"):
                break
            print("Please enter 'y' or 'n'.")
        approved = answer == "y"
        trace["human_gate"] = {
            "enabled": True,
            "decision": "approved" if approved else "rejected",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        return approved

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

        # Optional human approval gate: strictly BETWEEN the Risk Engine PASS
        # and Execution Service submission. The Risk Engine is the sole hard
        # deterministic boundary; this is an additional soft checkpoint.
        if config.HUMAN_GATE and not self._human_gate(proposal, trace):
            raise HumanRejectedError("human gate declined at risk-pass checkpoint")

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

        # Strategist gets full-tag retrieval (regime tags now known from L1).
        strat_ctx = retrieve_for_agent(
            "strategist", ticker=ticker,
            market_regime=l1[0].get("market_regime"),
            volatility_regime=l1[1].get("volatility_regime"),
        )

        if config.ENABLE_DUAL_STRATEGIST:
            p1 = self.strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3], past_context=strat_ctx,
            )
            p2 = self.conservative_strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3], past_context=strat_ctx,
            )
            proposal, arb_meta = arbitrate_proposals(p1, p2)
            trace["dual_strategist"] = {
                "enabled": True,
                "primary_proposal": p1,
                "secondary_proposal": p2,
                "arbitration": arb_meta,
            }
        else:
            proposal = self.strategist.synthesize(
                ticker, l1[0], l1[1], l1[2], l1[3], past_context=strat_ctx,
            )
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
        except HumanRejectedError as e:
            # Human declined at the risk-pass checkpoint: end this cycle exactly
            # like a Mentor REJECT -- NO_TRADE, no order submitted, no retry
            # within the same cycle.
            logger.warning("human gate: %s", e)
            trace["execution"] = {"status": "REJECTED_BY_HUMAN", "detail": str(e)}
            trace["final"] = "NO_TRADE"
            trace["reason"] = (
                "human gate declined after risk passed "
                "(mentor REJECT-equivalent; no order, no retry)"
            )
            record_cycle(trace)
            return trace
        except Exception as e:  # execution must never crash the trace
            logger.exception("execution error")
            trace["execution"] = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"}
        record_cycle(trace)
        return trace
