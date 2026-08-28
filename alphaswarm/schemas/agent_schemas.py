"""Fixed agent I/O schemas (LOCKED).

These mirror 02_TRD.md Section 4 exactly. The Mentor's targeted-correction
mechanism, the Strategist's synthesis, and downstream validation all depend
on these field names -- do NOT rename, add, or remove fields. Malformed
agent output is a build error to fix, never something to route around.
"""

from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Layer-1 agent required output fields (exact names, per TRD Section 4)
# ---------------------------------------------------------------------------
MARKET_SCHEMA: List[str] = [
    "market_regime",
    "directional_bias",
    "confidence",
    "supporting_evidence",
    "contradictory_evidence",
    "risk_factors",
]

VOLATILITY_SCHEMA: List[str] = [
    "volatility_regime",
    "iv_assessment",
    "realized_vol_assessment",
    "term_structure_assessment",
    "confidence",
    "evidence",
    "warnings",
]

OPTIONS_SCHEMA: List[str] = [
    "candidate_structures",
    "contract_candidates",
    "structure_rationale",
    "greeks",
    "liquidity_assessment",
    "payoff_profile",
    "risks",
    "confidence",
]

PORTFOLIO_SCHEMA: List[str] = [
    "current_exposure",
    "portfolio_impact",
    "concentration_risk",
    "correlation_risk",
    "conflicts",
    "recommendation",
]

# ---------------------------------------------------------------------------
# Strategist output (per TRD Section 4) -- a full trade proposal, or NO_TRADE.
# ---------------------------------------------------------------------------
STRATEGIST_NO_TRADE = "NO_TRADE"

STRATEGIST_SCHEMA: List[str] = [
    "underlying",
    "market_thesis",
    "volatility_thesis",
    "selected_structure",
    "contract",
    "rationale",
    "alternative_structures_considered",
    "entry_conditions",
    "exit_conditions",
    "invalidation_conditions",
    "portfolio_impact",
    "max_loss",
    "key_risks",
    "confidence",
    "reasons_not_to_trade",
]

# ---------------------------------------------------------------------------
# Mentor output (strict, machine-readable JSON) -- per TRD Section 4.
# ---------------------------------------------------------------------------
MENTOR_DECISIONS = ["APPROVE", "REVISE", "REJECT", "WAIT"]
MENTOR_SEVERITIES = ["low", "medium", "high"]

MENTOR_IMPERFECTION_SCHEMA: Dict[str, Any] = {
    "component": "string",
    "owner": "agent_name",
    "severity": "low | medium | high",
    "reason": "string",
    "action": "string",
    "invalidate_downstream": "bool",
}

MENTOR_SCHEMA: Dict[str, Any] = {
    "overall_decision": "APPROVE | REVISE | REJECT | WAIT",
    "imperfections": [MENTOR_IMPERFECTION_SCHEMA],
}

# ---------------------------------------------------------------------------
# Registry: agent name -> required top-level fields.
# ---------------------------------------------------------------------------
AGENT_SCHEMAS: Dict[str, List[str]] = {
    "market_agent": MARKET_SCHEMA,
    "volatility_agent": VOLATILITY_SCHEMA,
    "options_agent": OPTIONS_SCHEMA,
    "portfolio_agent": PORTFOLIO_SCHEMA,
    "strategist": STRATEGIST_SCHEMA,
    "mentor": list(MENTOR_SCHEMA.keys()),
}


def validate_agent_output(agent: str, output: Any) -> tuple[bool, List[str]]:
    """Return (ok, errors) for one agent's structured output.

    Pure validation only -- no LLM calls. Checks that every required field
    (exact name, per the locked schemas) is present. The Strategist is also
    allowed to return the literal NO_TRADE value.
    """
    errors: List[str] = []

    if agent == "strategist" and output == STRATEGIST_NO_TRADE:
        return True, []

    if not isinstance(output, dict):
        return False, [f"{agent} output must be a JSON object"]

    if agent == "mentor":
        _validate_mentor(output, errors)
    elif agent in AGENT_SCHEMAS:
        for field in AGENT_SCHEMAS[agent]:
            if field not in output:
                errors.append(f"missing required field '{field}'")
    else:
        errors.append(f"unknown agent '{agent}'")

    return (len(errors) == 0, errors)


def _validate_mentor(output: Dict[str, Any], errors: List[str]) -> None:
    decision = output.get("overall_decision")
    if decision is None:
        errors.append("missing required field 'overall_decision'")
    elif decision not in MENTOR_DECISIONS:
        errors.append(
            f"overall_decision must be one of {MENTOR_DECISIONS}, got {decision!r}"
        )

    imperfections = output.get("imperfections")
    if not isinstance(imperfections, list):
        errors.append("'imperfections' must be a list")
        return

    for i, imp in enumerate(imperfections):
        if not isinstance(imp, dict):
            errors.append(f"imperfections[{i}] must be an object")
            continue
        for field in MENTOR_IMPERFECTION_SCHEMA:
            if field not in imp:
                errors.append(f"imperfections[{i}] missing '{field}'")
        sev = imp.get("severity")
        if sev is not None and sev not in MENTOR_SEVERITIES:
            errors.append(
                f"imperfections[{i}].severity must be one of {MENTOR_SEVERITIES}"
            )
        ivd = imp.get("invalidate_downstream")
        if ivd is not None and not isinstance(ivd, bool):
            errors.append(f"imperfections[{i}].invalidate_downstream must be a bool")
