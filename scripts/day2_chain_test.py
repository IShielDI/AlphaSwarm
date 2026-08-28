"""Day 2 test: full Layer 1 -> Strategist chain on real market snapshots.

Usage:
    python scripts/day2_chain_test.py SPY NVDA MSFT   # run full chain per ticker
    python scripts/day2_chain_test.py --no-trade-test # strategist NO_TRADE check only

Halts on any agent failing schema validation twice in a row (Agent Rules 5).
"""

from __future__ import annotations

import json
import sys

from alphaswarm.agents.llm_client import AgentSchemaError, LLMError
from alphaswarm.agents.market_agent import MarketAgent
from alphaswarm.agents.options_agent import OptionsAgent
from alphaswarm.agents.portfolio_agent import PortfolioAgent
from alphaswarm.agents.strategist import Strategist
from alphaswarm.agents.volatility_agent import VolatilityAgent

STRATEGIST = Strategist()
MARKET = MarketAgent()
VOL = VolatilityAgent()
OPTIONS = OptionsAgent()
PORTFOLIO = PortfolioAgent()


def show(label: str, value) -> None:
    print(f"\n{'=' * 30} {label} {'=' * 30}")
    print(json.dumps(value, indent=2, default=str))


def run_chain(ticker: str) -> None:
    print(f"\n{'#' * 70}\n# DECISION CYCLE: {ticker}\n{'#' * 70}")

    market = MARKET.analyze(ticker)
    show(f"{ticker} MARKET AGENT", market)

    vol = VOL.analyze(ticker)
    show(f"{ticker} VOLATILITY AGENT", vol)

    options = OPTIONS.analyze(
        ticker,
        context={
            "market_regime": market["market_regime"],
            "directional_bias": market["directional_bias"],
            "volatility_regime": vol["volatility_regime"],
            "iv_assessment": vol["iv_assessment"],
        },
    )
    show(f"{ticker} OPTIONS AGENT", options)

    portfolio = PORTFOLIO.analyze(
        ticker,
        context={
            "proposed_structure": options["candidate_structures"],
            "contract_candidates": options["contract_candidates"],
        },
    )
    show(f"{ticker} PORTFOLIO AGENT", portfolio)

    proposal = STRATEGIST.synthesize(ticker, market, vol, options, portfolio)
    show(f"{ticker} STRATEGIST", proposal)

    verdict = (
        "NO_TRADE" if proposal == "NO_TRADE"
        else f"TRADE: {proposal['selected_structure']} "
             f"{proposal['contract'].get('short_leg', {}).get('symbol')} / "
             f"{proposal['contract'].get('long_leg', {}).get('symbol')}"
    )
    print(f"\n>>> {ticker} FINAL: {verdict}")


def no_trade_test() -> None:
    """Item 5 test: disagreeing signals must yield NO_TRADE, not a forced trade."""
    print("\n" + "#" * 70 + "\n# NO_TRADE TEST: signals disagree\n" + "#" * 70)
    market = {
        "market_regime": "trending_up",
        "directional_bias": "bullish",
        "confidence": 0.75,
        "supporting_evidence": ["spot above sma_20 and sma_50", "positive 20d return"],
        "contradictory_evidence": ["volume below average"],
        "risk_factors": ["resistance near 60d high"],
    }
    vol = {
        "volatility_regime": "high",
        "iv_assessment": "extremely expensive, IV 0.55 vs realized 0.18 -- richly priced",
        "realized_vol_assessment": "realized vol low and stable at 18%",
        "term_structure_assessment": "severe backwardation, near-term event premium priced in",
        "confidence": 0.85,
        "evidence": ["ATM IV 55% vs 20d realized 18%", "IV rank near 95%"],
        "warnings": ["selling premium here means selling overpriced protection INTO an event"],
    }
    options = {
        "candidate_structures": ["bull_put_spread"],
        "contract_candidates": [
            {
                "structure": "bull_put_spread",
                "short_leg": {"symbol": "SPY260918P00750000", "strike": 750.0},
                "long_leg": {"symbol": "SPY260918P00745000", "strike": 745.0},
                "estimated_credit": 0.65,
                "max_loss_per_contract": 435.0,
                "dte": 21,
            }
        ],
        "structure_rationale": "only structure consistent with bullish bias",
        "greeks": {"short_leg": {"delta": -0.15, "gamma": 0.01, "theta": -0.2, "vega": 0.25}},
        "liquidity_assessment": "wide markets, 30-40% bid/ask width, fills unrealistic",
        "payoff_profile": "max profit $65, max loss $435, breakeven 749.35",
        "risks": ["gap risk through short strike", "poor fills"],
        "confidence": 0.4,
    }
    portfolio = {
        "current_exposure": "equity $99,975; existing SPY put position",
        "portfolio_impact": "adding credit spread duplicates underlying exposure",
        "concentration_risk": "SPY already largest single-underlying exposure",
        "correlation_risk": "perfect correlation with existing SPY position",
        "conflicts": ["new bull put conflicts with existing long put direction"],
        "recommendation": "do_not_proceed",
    }
    result = STRATEGIST.synthesize("SPY", market, vol, options, portfolio)
    show("STRATEGIST (disagreeing signals)", result)
    if result == "NO_TRADE":
        print("\n>>> NO_TRADE TEST PASSED: strategist refused to force a trade.")
    else:
        print("\n>>> NO_TRADE TEST FAILED: strategist forced a proposal despite "
              "disagreeing signals and a do_not_proceed recommendation.")
        sys.exit(1)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        args = ["--no-trade-test", "SPY", "NVDA", "MSFT"]
    if "--no-trade-test" in args:
        args.remove("--no-trade-test")
        no_trade_test()
    for ticker in args:
        try:
            run_chain(ticker)
        except (AgentSchemaError, LLMError) as e:
            print(f"\nHALT on {ticker}: {e}", file=sys.stderr)
            sys.exit(2)


if __name__ == "__main__":
    main()