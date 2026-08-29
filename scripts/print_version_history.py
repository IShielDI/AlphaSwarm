#!/usr/bin/env python
"""Print the version history from versions.jsonl in a human-readable format.

Usage:
    python scripts/print_version_history.py [path/to/versions.jsonl]

If no path is given, the default project-root locations/AlphaSwarm/versions.jsonl
is used.
"""
from __future__ import annotations

import sys

from alphaswarm.improve.improvement_engine import VERSIONS_PATH, load_versions


def print_version_history(path: str | None = None) -> None:
    p = path or VERSIONS_PATH
    records = load_versions(path)
    if not records:
        print(f"No version records found at {p}")
        return
    print(f"Version history ({len(records)} records) from {p}")
    print("=" * 72)
    for r in records:
        print()
        print(f"  Version {r['version']}  |  {r['timestamp']}")
        print(f"  Decision: {r['promotion_decision']}")
        print(f"  Agent: {r.get('agent', '?')}")
        print(f"  Change: {r['change_description']}")
        imps = r.get("triggering_imperfection", [])
        print(f"  Triggering imperfection: "
              f"{'; '.join(imps) if imps else '(none)'}")
        notes = r.get("mentor_notes", {})
        print(f"  Mentor reasoning: {notes.get('reasoning', '(none)')}")
        conds = notes.get("conditions", [])
        if conds:
            print(f"  Conditions: {'; '.join(conds)}")
        caveat = notes.get("sample_size_caveat", "")
        if caveat:
            print(f"  Sample-size caveat: {caveat}")
        prev = r.get("previous_version")
        if prev:
            print(f"  Previous version ref: v{prev['version']} "
                  "(config snapshot available for rollback)")
        else:
            print("  Previous version ref: <initial version, no prior config>")
        print("-" * 72)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else None
    print_version_history(path)
