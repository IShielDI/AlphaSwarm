"""Decision Store -- append-only JSONL trace of every decision cycle.

Each cycle appends one JSON object (inputs, L1 outputs, proposal, mentor
audits, corrections, risk result, execution result). Used by the Position
Monitor and for post-trade audit. No LLM involvement.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict

from . import config

logger = logging.getLogger(__name__)

DEFAULT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "decisions.jsonl")


def record_cycle(trace: Dict[str, Any], path: str = DEFAULT_PATH) -> str:
    trace = dict(trace)
    # Every record carries a consistent `human_gate` shape regardless of mode.
    # When the optional gate runs, the orchestrator writes the full object
    # (enabled + decision + timestamp); otherwise we persist enabled:false so
    # the key is never omitted from a record.
    trace.setdefault("human_gate", {"enabled": bool(config.HUMAN_GATE)})
    trace.setdefault("recorded_at", time.strftime("%Y-%m-%dT%H:%M:%S%z"))
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(trace, indent=2, default=str) + "\n")
    logger.info("decision cycle recorded to %s", path)
    return path
