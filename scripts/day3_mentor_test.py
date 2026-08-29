import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from alphaswarm.agents.mentor import Mentor
from alphaswarm.schemas.agent_schemas import validate_agent_output

# ---------------------------------------------------------------------------
# Case 1: clean, internally consistent proposal -> expect APPROVE
# ---------------------------------------------------------------------------
CASE_APPROVE = dict(
    ticker="AAPL",
    proposal={
        "underlying": "AAPL", "selected_structure": "bull_put_spread",
        "market_thesis": "Short-term uptrend, spot above SMA20/SMA50, positive 20d return; moderate conviction on below-average volume.",
        "volatility_thesis": "IV modestly above realized vol across 7-21 DTE; contango; selling premium at 14 DTE attractive.",
        "contract": {
            "short_leg": {"symbol": "AAPL260911P00315000", "strike": 315.0},
            "long_leg": {"symbol": "AAPL260911P00310000", "strike": 310.0},
            "expiration": "260911", "estimated_credit": 1.10,
            "max_loss_per_contract": 390.0,
        },
        "rationale": "Bull put aligned with bullish bias; IV rich vs realized; $1.10 credit on $5 width; breakeven 313.90 below SMA20.",
        "alternative_structures_considered": [
            "bear_call_spread -- rejected, contradicts bullish market bias",
            "naked_short_put -- rejected, out of scope (credit spreads only)",
        ],
        "entry_conditions": ["spot above 318.50 at entry", "credit >= 1.05"],
        "exit_conditions": ["take profit at 50% max profit", "stop at 2x credit"],
        "invalidation_conditions": ["spot closes below SMA20 309.88", "IV spike with spot decline"],
        "portfolio_impact": "No AAPL exposure currently; max loss < 0.4% of equity; diversifies SPY-only book.",
        "max_loss": 390.0, "confidence": 0.78,
        "key_risks": ["low volume conviction", "14 DTE gamma near short strike"],
        "reasons_not_to_trade": [
            "volume ratio 0.47 suggests weak institutional participation",
            "SMA20 below SMA50 is a longer-term bearish cross",
        ],
    },
    market={
        "market_regime": "trending_up", "directional_bias": "bullish", "confidence": 0.8,
        "supporting_evidence": ["spot above SMA20 and SMA50", "+3.5% 5d return"],
        "contradictory_evidence": ["volume ratio 0.47"],
        "risk_factors": ["resistance near 60d high"],
    },
    vol={
        "volatility_regime": "normal", "iv_assessment": "modestly rich vs realized (22% IV vs 19% realized)",
        "realized_vol_assessment": "stable near 19%", "term_structure_assessment": "contango",
        "confidence": 0.8, "evidence": ["14 DTE IV 22% vs 19% realized"], "warnings": [],
    },
    options={
        "candidate_structures": ["bull_put_spread"],
        "contract_candidates": [{
            "structure": "bull_put_spread",
            "short_leg": {"symbol": "AAPL260911P00315000", "strike": 315.0},
            "long_leg": {"symbol": "AAPL260911P00310000", "strike": 310.0},
            "estimated_credit": 1.10, "max_loss_per_contract": 390.0, "dte": 14,
        }],
        "structure_rationale": "only structure fitting bullish bias within scope",
        "greeks": {"AAPL260911P00315000": {"delta": -0.25, "gamma": 0.02, "theta": -0.3, "vega": 0.2}},
        "liquidity_assessment": "tight markets, realistic mid fills",
        "payoff_profile": "max profit $110, max loss $390, breakeven 313.90",
        "risks": ["directional", "vega"], "confidence": 0.85,
    },
    portfolio={
        "current_exposure": "equity ~$100k; SPY-only option exposure",
        "portfolio_impact": "new underlying; risk < 0.4% equity",
        "concentration_risk": "reduces SPY concentration",
        "correlation_risk": "moderate positive correlation with SPY",
        "conflicts": [], "recommendation": "proceed",
    },
)


# ---------------------------------------------------------------------------
# Case 2: strategist builds a bull put on a BEARISH market call
#         -> expect REVISE/REJECT with owner=strategist (or market_agent)
# ---------------------------------------------------------------------------
CASE_DIRECTION_CONFLICT = dict(
    ticker="TSLA",
    proposal={
        "underlying": "TSLA", "selected_structure": "bull_put_spread",
        "market_thesis": "Ignored the bearish regime call; thesis claims support holding.",
        "volatility_thesis": "IV elevated; premium selling attractive regardless of direction.",
        "contract": {
            "short_leg": {"symbol": "TSLA260911P00320000", "strike": 320.0},
            "long_leg": {"symbol": "TSLA260911P00310000", "strike": 310.0},
            "expiration": "260911", "estimated_credit": 3.20,
            "max_loss_per_contract": 680.0,
        },
        "rationale": "High credit; support at 320.",
        "alternative_structures_considered": ["bear_call_spread -- less credit"],
        "entry_conditions": ["credit >= 3.0"], "exit_conditions": ["50% profit"],
        "invalidation_conditions": ["spot below 310"],
        "portfolio_impact": "small position", "max_loss": 680.0, "confidence": 0.6,
        "key_risks": ["downtrend"], "reasons_not_to_trade": ["market agent is bearish"],
    },
    market={
        "market_regime": "trending_down", "directional_bias": "bearish", "confidence": 0.85,
        "supporting_evidence": ["lower highs", "below SMA50"],
        "contradictory_evidence": [], "risk_factors": ["momentum accelerating down"],
    },
    vol={
        "volatility_regime": "high", "iv_assessment": "rich (45% IV vs 30% realized)",
        "realized_vol_assessment": "elevated 30%", "term_structure_assessment": "backwardation",
        "confidence": 0.8, "evidence": ["IV 45%"], "warnings": ["event risk priced"],
    },
    options={
        "candidate_structures": ["bull_put_spread", "bear_call_spread"],
        "contract_candidates": [{
            "structure": "bull_put_spread",
            "short_leg": {"symbol": "TSLA260911P00320000", "strike": 320.0},
            "long_leg": {"symbol": "TSLA260911P00310000", "strike": 310.0},
            "estimated_credit": 3.20, "max_loss_per_contract": 680.0, "dte": 11,
        }],
        "structure_rationale": "both structures offered; credit similar",
        "greeks": {"TSLA260911P00320000": {"delta": -0.35, "gamma": 0.03, "theta": -0.5, "vega": 0.4}},
        "liquidity_assessment": "adequate", "payoff_profile": "credit 320, risk 680",
        "risks": ["counter-trend trade"], "confidence": 0.7,
    },
    portfolio={
        "current_exposure": "no TSLA exposure", "portfolio_impact": "new underlying",
        "concentration_risk": "low", "correlation_risk": "moderate",
        "conflicts": [], "recommendation": "proceed_with_caution",
    },
)

# ---------------------------------------------------------------------------
# Case 3: strategist quotes credit inconsistent with the options surface
#         -> expect imperfection with owner=options_agent or strategist
# ---------------------------------------------------------------------------
CASE_FABRICATED_CREDIT = dict(
    ticker="NVDA",
    proposal={
        "underlying": "NVDA", "selected_structure": "bull_put_spread",
        "market_thesis": "Uptrend intact above SMA20.",
        "volatility_thesis": "IV near realized; neutral premium.",
        "contract": {
            "short_leg": {"symbol": "NVDA260911P00180000", "strike": 180.0},
            "long_leg": {"symbol": "NVDA260911P00175000", "strike": 175.0},
            "expiration": "260911", "estimated_credit": 2.40,
            "max_loss_per_contract": 260.0,
        },
        "rationale": "2.40 credit is excellent on 5-wide.",
        "alternative_structures_considered": ["bear_call_spread -- worse fit"],
        "entry_conditions": ["credit >= 2.40"], "exit_conditions": ["50% profit"],
        "invalidation_conditions": ["spot below 175"],
        "portfolio_impact": "within limits", "max_loss": 260.0, "confidence": 0.75,
        "key_risks": ["assignment"], "reasons_not_to_trade": ["credit may be optimistic"],
    },
    market={
        "market_regime": "trending_up", "directional_bias": "bullish", "confidence": 0.75,
        "supporting_evidence": ["above SMA20"], "contradictory_evidence": [],
        "risk_factors": [],
    },
    vol={
        "volatility_regime": "normal", "iv_assessment": "near realized",
        "realized_vol_assessment": "35%", "term_structure_assessment": "flat",
        "confidence": 0.75, "evidence": ["IV 36%"], "warnings": [],
    },
    options={
        "candidate_structures": ["bull_put_spread"],
        "contract_candidates": [{
            "structure": "bull_put_spread",
            "short_leg": {"symbol": "NVDA260911P00180000", "strike": 180.0},
            "long_leg": {"symbol": "NVDA260911P00175000", "strike": 175.0},
            "estimated_credit": 0.85, "max_loss_per_contract": 415.0, "dte": 11,
        }],
        "structure_rationale": "fits bias",
        "greeks": {"NVDA260911P00180000": {"delta": -0.22, "gamma": 0.02, "theta": -0.28, "vega": 0.19}},
        "liquidity_assessment": "mid-market credit from actual bid/ask is ~0.85",
        "payoff_profile": "max profit 85, max loss 415, breakeven 179.15",
        "risks": ["directional"], "confidence": 0.8,
    },
    portfolio={
        "current_exposure": "no NVDA exposure", "portfolio_impact": "small",
        "concentration_risk": "low", "correlation_risk": "moderate",
        "conflicts": [], "recommendation": "proceed",
    },
)

# ---------------------------------------------------------------------------
# Case 4: proposal ignores portfolio conflict + unactionable conditions
#         -> expect imperfections with owner=strategist / portfolio_agent
# ---------------------------------------------------------------------------
CASE_CONFLICT_IGNORED = dict(
    ticker="SPY",
    proposal={
        "underlying": "SPY", "selected_structure": "bull_put_spread",
        "market_thesis": "Bullish; uptrend above SMAs.",
        "volatility_thesis": "IV cheap; sell premium.",
        "contract": {
            "short_leg": {"symbol": "SPY260911P00755000", "strike": 755.0},
            "long_leg": {"symbol": "SPY260911P00750000", "strike": 750.0},
            "expiration": "260911", "estimated_credit": 0.90,
            "max_loss_per_contract": 410.0,
        },
        "rationale": "Standard bull put on bullish bias.",
        "alternative_structures_considered": ["bear_call_spread"],
        "entry_conditions": ["any time"], "exit_conditions": ["eventually"],
        "invalidation_conditions": ["if things go badly"],
        "portfolio_impact": "fine", "max_loss": 410.0, "confidence": 0.8,
        "key_risks": ["directional"], "reasons_not_to_trade": ["existing SPY puts"],
    },
    market={
        "market_regime": "trending_up", "directional_bias": "bullish", "confidence": 0.7,
        "supporting_evidence": ["above SMAs"], "contradictory_evidence": [],
        "risk_factors": [],
    },
    vol={
        "volatility_regime": "low", "iv_assessment": "cheap",
        "realized_vol_assessment": "10%", "term_structure_assessment": "mild contango",
        "confidence": 0.85, "evidence": ["IV 11%"], "warnings": [],
    },
    options={
        "candidate_structures": ["bull_put_spread"],
        "contract_candidates": [{
            "structure": "bull_put_spread",
            "short_leg": {"symbol": "SPY260911P00755000", "strike": 755.0},
            "long_leg": {"symbol": "SPY260911P00750000", "strike": 750.0},
            "estimated_credit": 0.90, "max_loss_per_contract": 410.0, "dte": 14,
        }],
        "structure_rationale": "fits bias",
        "greeks": {"SPY260911P00755000": {"delta": -0.18, "gamma": 0.015, "theta": -0.2, "vega": 0.22}},
        "liquidity_assessment": "tight",
        "payoff_profile": "max profit 90, max loss 410",
        "risks": ["directional"], "confidence": 0.85,
    },
    portfolio={
        "current_exposure": "existing SPY put spread 755/750 exp 260908 (short 2, long 2)",
        "portfolio_impact": "duplicate structure in same underlying, overlapping strikes",
        "concentration_risk": "increases SPY at-risk exposure",
        "correlation_risk": "perfect correlation with existing position",
        "conflicts": ["new spread duplicates the open 755/750 bull put"],
        "recommendation": "do_not_proceed",
    },
)

CASES = [
    ("clean_proposal", CASE_APPROVE),
    ("direction_conflict", CASE_DIRECTION_CONFLICT),
    ("fabricated_credit", CASE_FABRICATED_CREDIT),
    ("portfolio_conflict_ignored", CASE_CONFLICT_IGNORED),
]


def main() -> None:
    mentor = Mentor()
    failures = 0
    for name, case in CASES:
        print(f"\n{'=' * 25} {name} {'=' * 25}")
        try:
            out = mentor.audit(
                case["ticker"], case["proposal"], case["market"],
                case["vol"], case["options"], case["portfolio"],
            )
        except Exception as e:
            print(f"SCHEMA/TRANSPORT FAILURE: {type(e).__name__}: {e}")
            failures += 1
            continue
        ok, errors = validate_agent_output("mentor", out)
        owners = {imp.get("owner") for imp in out.get("imperfections", [])}
        print(f"decision={out.get('overall_decision')}  "
              f"n_imperfections={len(out.get('imperfections', []))}  owners={owners}")
        for imp in out.get("imperfections", []):
            print(f"  - [{imp.get('severity')}] {imp.get('component')} "
                  f"(owner={imp.get('owner')}, invalidates={imp.get('invalidate_downstream')})")
            print(f"    reason: {imp.get('reason')}")
            print(f"    action: {imp.get('action')}")
        if not ok:
            print(f"SCHEMA ERRORS: {errors}")
            failures += 1
        else:
            print("schema: EXACT MATCH")

    print(f"\n{'#' * 60}")
    print(f"RESULT: {len(CASES) - failures}/{len(CASES)} cases schema-exact")
    if failures:
        print("STANDALONE VALIDATION FAILED -- do NOT wire the Mentor into the loop.")
        sys.exit(1)
    print("Standalone Mentor validation PASSED -- safe to wire into the loop.")


if __name__ == "__main__":
    main()
