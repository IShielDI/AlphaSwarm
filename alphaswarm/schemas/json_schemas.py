"""JSON-Schema definitions for provider-level structured output.

Used by llm_client to pass `response_format: {type: json_schema}` to
OpenRouter (structured_outputs) for the agents whose output is always a
JSON object with fixed fields (market, volatility, portfolio, mentor).

Deliberately NOT covered here:
  * options_agent -- `greeks` has dynamic keys (structure or OCC symbol
    names), which strict JSON-Schema mode cannot express; it stays on
    prompt instructions + parse validation.
  * strategist -- may return the literal JSON string "NO_TRADE" instead
    of an object; a forced object schema would forbid that valid result.
    It stays on Gemini's responseMimeType=application/json.

Schemas mirror AGENT_SCHEMAS in agent_schemas.py exactly -- if you change
one, change both (the runtime validation is AGENT_SCHEMAS; this is a
generation-time constraint only, never trusted instead of validation).
"""

from __future__ import annotations

import copy


def _str_enum(values) -> dict:
    return {"type": "string", "enum": list(values)}


def _str_array() -> dict:
    return {"type": "array", "items": {"type": "string"}}


def _obj(props: dict, additional: bool = False) -> dict:
    return {
        "type": "object",
        "properties": props,
        "required": sorted(props.keys()),
        "additionalProperties": additional,
    }


def _strict(obj: dict) -> dict:
    """Deep-copy with additionalProperties=False everywhere (strict mode)."""
    s = copy.deepcopy(obj)

    def _walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                node["additionalProperties"] = False
                for v in node["properties"].values():
                    _walk(v)
            for key in ("items",):
                if key in node:
                    _walk(node[key])
        elif isinstance(node, list):
            for item in node:
                _walk(item)

    _walk(s)
    return s


MARKET_JSON_SCHEMA = _strict(_obj({
    "market_regime": {"type": "string"},
    "directional_bias": {"type": "string"},
    "confidence": {"type": "number"},
    "supporting_evidence": _str_array(),
    "contradictory_evidence": _str_array(),
    "risk_factors": _str_array(),
}))

VOLATILITY_JSON_SCHEMA = _strict(_obj({
    "volatility_regime": {"type": "string"},
    "iv_assessment": {"type": "string"},
    "realized_vol_assessment": {"type": "string"},
    "term_structure_assessment": {"type": "string"},
    "confidence": {"type": "number"},
    "evidence": _str_array(),
    "warnings": _str_array(),
}))

PORTFOLIO_JSON_SCHEMA = _strict(_obj({
    "current_exposure": {"type": "string"},
    "portfolio_impact": {"type": "string"},
    "concentration_risk": {"type": "string"},
    "correlation_risk": {"type": "string"},
    "conflicts": _str_array(),
    "recommendation": {"type": "string"},
}))

_MENTOR_IMPERFECTION = _obj({
    "component": {"type": "string"},
    "owner": _str_enum([
        "market_agent", "volatility_agent", "options_agent",
        "portfolio_agent", "strategist", "none",
    ]),
    "severity": _str_enum(["low", "medium", "high"]),
    "reason": {"type": "string"},
    "action": {"type": "string"},
    "invalidate_downstream": {"type": "boolean"},
})

MENTOR_JSON_SCHEMA = _strict(_obj({
    "overall_decision": _str_enum(["APPROVE", "REVISE", "REJECT", "WAIT"]),
    "imperfections": {"type": "array", "items": _MENTOR_IMPERFECTION},
}))

# agent name -> (JSON schema, strict)
JSON_SCHEMAS = {
    "market_agent": (MARKET_JSON_SCHEMA, True),
    "volatility_agent": (VOLATILITY_JSON_SCHEMA, True),
    "portfolio_agent": (PORTFOLIO_JSON_SCHEMA, True),
    "mentor": (MENTOR_JSON_SCHEMA, True),
}