"""Deterministic integration validation of the Phase 5.1 HUMAN_GATE.

Drives the REAL orchestrator.run_cycle / _execute / _human_gate and the REAL
decision_store.record_cycle code paths, but with stubbed LLM agents and a
stubbed Alpaca/execution layer so the cycle deterministically reaches the
risk-PASS checkpoint. This is the authoritative proof of the gate because a
live cycle is not guaranteed to reach execution (the system often NO_TRADEs).

Covers the three required validations:
  1. HUMAN_GATE=False -> record has human_gate:{enabled:false}, order submits.
  2. HUMAN_GATE=True, answer "y" -> order submits, human_gate enabled/approved.
  3. HUMAN_GATE=True, answer "n" -> NO order, cycle ends like a Mentor REJECT
     (final=NO_TRADE, no retry).

Run with:  python tests/test_human_gate_integration.py
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
import unittest.mock
from types import SimpleNamespace

from alphaswarm import config
from alphaswarm import decision_store as ds
from alphaswarm import orchestrator as orch

_PROPOSAL = {
    "underlying": "AAPL",
    "selected_structure": "bull_put_spread",
    "market_thesis": "Uptrend.",
    "volatility_thesis": "IV rich.",
    "contract": {
        "short_leg": {"symbol": "AAPL260911P00315000", "strike": 315.0},
        "long_leg": {"symbol": "AAPL260911P00310000", "strike": 310.0},
        "expiration": "260911",
        "estimated_credit": 1.10,
        "max_loss_per_contract": 390.0,
    },
    "rationale": "fit",
    "alternative_structures_considered": ["bear_call_spread"],
    "entry_conditions": ["spot above 318"],
    "exit_conditions": ["take profit at 50% max profit"],
    "invalidation_conditions": ["close below SMA20"],
    "portfolio_impact": "within limits",
    "max_loss": 390.0,
    "confidence": 0.7,
    "key_risks": ["directional"],
    "reasons_not_to_trade": ["low volume"],
}


class _L1:
    def analyze(self, ticker, **kwargs):
        # Return a superset of keys so any Layer-1 agent (market/vol/options/
        # portfolio) can access whatever field _run_layer1 reads from it.
        return {
            "market_regime": "trending_up",
            "directional_bias": "bullish",
            "volatility_regime": "normal",
            "iv_assessment": "rich",
            "candidate_structures": ["bull_put_spread"],
            "contract_candidates": [
                {
                    "symbol": "AAPL260911P00315000",
                    "strike": 315.0,
                    "short_symbol": "AAPL260911P00315000",
                    "long_symbol": "AAPL260911P00310000",
                },
            ],
        }


class _Strat:
    def synthesize(self, *args, **kwargs):
        return _PROPOSAL


class _Mentor:
    def audit(self, *args, **kwargs):
        return {"overall_decision": "APPROVE", "imperfections": []}


class _Risk:
    def check(self, trade, equity, **kwargs):
        return SimpleNamespace(passed=True, failed_checks=[], checks=[], summary=lambda: "PASS")


class _Exec:
    def __init__(self):
        self.submitted = []

    def build_bull_put_spread(self, short_symbol, long_symbol):
        return ["legA", "legB"]

    def build_bear_call_spread(self, short_symbol, long_symbol):
        return ["legA", "legB"]

    def submit_spread(self, legs, qty, order_type="limit", limit_price=None,
                      time_in_force="day", client_order_id=None):
        self.submitted.append({"legs": legs, "qty": qty, "limit_price": limit_price})
        return SimpleNamespace(id="test-order", status="accepted")


class _Alpaca:
    def get_account_summary(self):
        return {"equity": 100000}


def build_orchestrator(exec_stub: _Exec) -> orch.Orchestrator:
    o = orch.Orchestrator()
    o.market = _L1()
    o.vol = _L1()
    o.options = _L1()
    o.portfolio = _L1()
    o.strategist = _Strat()
    o.mentor = _Mentor()
    o.risk_engine = _Risk()
    o.execution = exec_stub
    o.alpaca = _Alpaca()
    return o


class TestHumanGateIntegration(unittest.TestCase):
    def setUp(self):
        self._old_human_gate = config.HUMAN_GATE
        self._old_record = orch.record_cycle
        self.tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        self.tmp_path = self.tmp.name
        self.tmp.close()
        real = ds.record_cycle

        def _record(trace):
            return real(dict(trace), self.tmp_path)

        orch.record_cycle = _record

    def tearDown(self):
        config.HUMAN_GATE = self._old_human_gate
        orch.record_cycle = self._old_record
        if os.path.exists(self.tmp_path):
            os.remove(self.tmp_path)

    def _records(self):
        # record_cycle writes pretty-printed (indent=2) JSON, one object after
        # another. Parse consecutive top-level objects rather than line-by-line.
        with open(self.tmp_path, encoding="utf-8") as f:
            text = f.read()
        decoder = json.JSONDecoder()
        idx = 0
        results = []
        while idx < len(text):
            while idx < len(text) and text[idx].isspace():
                idx += 1
            if idx >= len(text):
                break
            obj, idx = decoder.raw_decode(text, idx)
            results.append(obj)
        return results

    # 1. HUMAN_GATE=False
    def test_gate_off_record_shape_and_execution(self):
        config.HUMAN_GATE = False
        exec_stub = _Exec()
        o = build_orchestrator(exec_stub)
        trace = o.run_cycle("AAPL", execute=True)

        self.assertEqual(trace["final"], "APPROVED")
        self.assertEqual(trace["execution"]["status"], "SUBMITTED")
        self.assertEqual(len(exec_stub.submitted), 1)  # order submitted normally
        records = self._records()
        self.assertEqual(len(records), 1)
        rec = records[0]
        # Every record has a consistent human_gate shape with enabled:false.
        self.assertEqual(rec["human_gate"], {"enabled": False})
        # Structure is otherwise the normal trace.
        for key in ("layer1", "proposal_v1", "mentor_audit_v1", "risk_engine", "execution"):
            self.assertIn(key, rec)

    # 2. HUMAN_GATE=True, answer "y"
    def test_gate_on_approved_submits(self):
        config.HUMAN_GATE = True
        exec_stub = _Exec()
        o = build_orchestrator(exec_stub)
        with unittest.mock.patch("builtins.input", return_value="y"):
            trace = o.run_cycle("AAPL", execute=True)

        self.assertEqual(trace["final"], "APPROVED")
        self.assertEqual(trace["execution"]["status"], "SUBMITTED")
        self.assertEqual(len(exec_stub.submitted), 1)  # proceeds to execution
        rec = self._records()[0]
        hg = rec["human_gate"]
        self.assertEqual(hg["enabled"], True)
        self.assertEqual(hg["decision"], "approved")
        self.assertIsInstance(hg["timestamp"], str)

    # 3. HUMAN_GATE=True, answer "n"
    def test_gate_on_rejected_submits_nothing(self):
        config.HUMAN_GATE = True
        exec_stub = _Exec()
        o = build_orchestrator(exec_stub)
        with unittest.mock.patch("builtins.input", return_value="n"):
            trace = o.run_cycle("AAPL", execute=True)

        # Ends the same way a Mentor REJECT does: NO_TRADE, no order, no retry.
        self.assertEqual(trace["final"], "NO_TRADE")
        self.assertEqual(trace["execution"]["status"], "REJECTED_BY_HUMAN")
        self.assertEqual(len(exec_stub.submitted), 0)  # NO order submitted
        rec = self._records()[0]
        hg = rec["human_gate"]
        self.assertEqual(hg["enabled"], True)
        self.assertEqual(hg["decision"], "rejected")
        self.assertIsInstance(hg["timestamp"], str)


if __name__ == "__main__":
    unittest.main(verbosity=2)
