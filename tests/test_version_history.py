"""Unit tests for the version recording mechanism in improvement_engine.

Tests both accept and reject verdicts, version number incrementing, and
previous-version config snapshot (rollback support) -- all with synthetic
data, no LLM calls required.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from alphaswarm.improve.improvement_engine import (
    REVIEW_SYSTEM_PROMPT,
    _next_version_number,
    load_versions,
    record_version,
)

# ---------------------------------------------------------------------------
# Synthetic fixtures (mirror the real hypothesis + review shapes)
# ---------------------------------------------------------------------------

_SYNTHETIC_HYPOTHESIS = {
    "agent": "strategist",
    "hypothesis": "strategist's weak area (NO_TRADE over-caution) may recur "
    "under similar conditions. Instrument future cycles to log this "
    "dimension explicitly.",
    "evidence": {
        "n_observations": 4,
        "weak_areas": [
            "NO_TRADE over-caution when Portfolio flags any conflict"
        ],
        "strength_areas": [
            "faithful synthesis of all four Layer-1 outputs"
        ],
    },
    "proposed_action": "add explicit logging/monitoring for this dimension; "
    "NO change to prompts, models, or risk parameters at this sample size",
}

_ACCEPT_REVIEW = {
    "verdict": "accept",
    "reasoning": "Hypothesis proposes instrumentation-only change -- safe to "
    "track given the n=4 weakness pattern. Caveat: n is too small for "
    "statistical validation.",
    "conditions": ["3 more cycles observed before any actual config change"],
    "sample_size_caveat": "n=4 observations from Day-3 trace; far too small "
    "for statistical validation.",
}

_REJECT_REVIEW = {
    "verdict": "reject",
    "reasoning": "Hypothesis targets a config change that would alter risk "
    "parameters; the evidence base is insufficient even for instrumentation.",
    "conditions": [],
    "sample_size_caveat": "n=2 observations; far too small to support even "
    "logging proposals.",
}


class TestVersionRecording(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)

    def tearDown(self) -> None:
        if os.path.exists(self.path):
            os.remove(self.path)

    def test_accept_writes_version_record(self) -> None:
        rec = record_version(_SYNTHETIC_HYPOTHESIS, _ACCEPT_REVIEW, path=self.path)
        self.assertEqual(rec["version"], 1)
        self.assertEqual(rec["promotion_decision"], "ACCEPTED")
        self.assertEqual(
            rec["change_description"], _SYNTHETIC_HYPOTHESIS["proposed_action"]
        )
        self.assertEqual(
            rec["triggering_imperfection"],
            _SYNTHETIC_HYPOTHESIS["evidence"]["weak_areas"],
        )
        self.assertEqual(rec["agent"], "strategist")
        self.assertEqual(
            rec["mentor_notes"]["reasoning"], _ACCEPT_REVIEW["reasoning"]
        )
        self.assertEqual(
            rec["mentor_notes"]["conditions"], _ACCEPT_REVIEW["conditions"]
        )
        self.assertEqual(
            rec["mentor_notes"]["sample_size_caveat"],
            _ACCEPT_REVIEW["sample_size_caveat"],
        )
        self.assertIsNone(rec["previous_version"])
        self.assertIn("review_system_prompt", rec["config_snapshot"])
        self.assertEqual(
            rec["config_snapshot"]["review_system_prompt"], REVIEW_SYSTEM_PROMPT
        )
        self.assertEqual(
            rec["config_snapshot"]["proposed_action"],
            _SYNTHETIC_HYPOTHESIS["proposed_action"],
        )

    def test_reject_writes_version_record(self) -> None:
        rec = record_version(_SYNTHETIC_HYPOTHESIS, _REJECT_REVIEW, path=self.path)
        self.assertEqual(rec["version"], 1)
        self.assertEqual(rec["promotion_decision"], "REJECTED")
        self.assertEqual(
            rec["change_description"], _SYNTHETIC_HYPOTHESIS["proposed_action"]
        )
        self.assertEqual(
            rec["triggering_imperfection"],
            _SYNTHETIC_HYPOTHESIS["evidence"]["weak_areas"],
        )
        self.assertIsNone(rec["previous_version"])

    def test_version_numbers_increment(self) -> None:
        r1 = record_version(_SYNTHETIC_HYPOTHESIS, _ACCEPT_REVIEW, path=self.path)
        r2 = record_version(_SYNTHETIC_HYPOTHESIS, _REJECT_REVIEW, path=self.path)
        self.assertEqual(r1["version"], 1)
        self.assertEqual(r2["version"], 2)

    def test_previous_version_stored_for_rollback(self) -> None:
        r1 = record_version(_SYNTHETIC_HYPOTHESIS, _ACCEPT_REVIEW, path=self.path)
        r2 = record_version(_SYNTHETIC_HYPOTHESIS, _REJECT_REVIEW, path=self.path)
        self.assertIsNotNone(r2["previous_version"])
        self.assertEqual(r2["previous_version"]["version"], 1)
        self.assertEqual(
            r2["previous_version"]["config_snapshot"],
            r1["config_snapshot"],
        )

    def test_load_versions_round_trip(self) -> None:
        record_version(_SYNTHETIC_HYPOTHESIS, _ACCEPT_REVIEW, path=self.path)
        record_version(_SYNTHETIC_HYPOTHESIS, _REJECT_REVIEW, path=self.path)
        records = load_versions(self.path)
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["version"], 1)
        self.assertEqual(records[1]["version"], 2)
        self.assertEqual(records[0]["promotion_decision"], "ACCEPTED")
        self.assertEqual(records[1]["promotion_decision"], "REJECTED")

    def test_next_version_number_empty_file(self) -> None:
        self.assertEqual(_next_version_number(self.path), 1)

    def test_load_versions_missing_file(self) -> None:
        missing = os.path.join(os.path.dirname(self.path), "does_not_exist.jsonl")
        self.assertEqual(load_versions(missing), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
