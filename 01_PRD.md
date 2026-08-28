# AlphaSwarm — Product Requirements Document (PRD)

## 1. Purpose

Build an autonomous, self-auditing multi-agent options trading system for the Alpaca AI Trading Agents Hackathon ("Options Alpha Agents" challenge), demonstrating a complete, real decision-to-execution cycle on Alpaca's $100,000 paper trading account within a 4-day build window.

## 2. Problem Statement

Most multi-agent trading demos are "agents vote, majority wins" systems with no real quality control between analysis and execution. AlphaSwarm's differentiator is a Mentor/Judge agent that audits a proposed trade **component by component**, routes corrections only to the responsible specialist agent, and gates every decision through a deterministic risk engine before any real order reaches Alpaca.

## 3. Target Outcome / Success Criteria

The build is successful if, by the end of Day 4, the system can demonstrate **one complete, real decision lifecycle**, live or recorded:

1. Real market/options data pulled from Alpaca
2. Four specialist agents independently produce structured analysis
3. Strategist synthesizes one trade proposal (or NO TRADE)
4. Mentor audits the proposal component-by-component and finds at least one real issue
5. Targeted correction sent only to the responsible agent
6. Revised proposal passes Mentor audit
7. Deterministic Risk Engine validates the trade
8. Real multi-leg order submitted and filled in Alpaca paper trading
9. Position tracked by the Position Monitor
10. After a trade closes: Outcome Analyzer produces a post-mortem, and one Improvement Engine hypothesis is generated and reviewed by the Mentor

A smaller working system that completes all 10 steps beats a larger system where any step is faked, mocked, or untested.

## 4. In Scope (Build This)

- Directional vertical credit spreads (bull put / bear call) on 5-8 liquid large-cap/ETF tickers
- Swing time horizon (7-21 DTE entry, closed before expiration)
- Four Layer-1 research agents (Market, Volatility, Options, Portfolio)
- One Strategist agent (considers 1-2 alternatives, can output NO TRADE)
- One Mentor/Judge agent (component audit, targeted correction, capped at ONE revision round)
- Deterministic Risk Engine (max loss, position size, concentration, duplicate-order checks — no LLM)
- Real Alpaca paper execution via multi-leg orders
- Position Monitor (scheduled HOLD/EXIT check)
- Light self-improvement: Outcome Analyzer + a running Imperfection Monitor log + ONE Improvement Engine pass reviewed by the Mentor
- Day 1 deterministic backtest of the entry rule against historical data (no LLM), to validate the strategy has real edge before building agents around it

## 5. Explicitly Out of Scope (Do Not Build)

- Multi-strategist layer (parallel competing strategists)
- Full versioning/promotion/rollback pipeline for strategy changes
- Retrieval-based agent memory across many historical situations
- Alpaca CLI (MCP Server only)
- Human approval gate (optional future addition, not required for this build)
- Open-ended multi-round Mentor loop (hard cap: one correction round)
- Any model fine-tuning / weight training
- Options structures other than vertical credit spreads (no naked options, no iron condors, no straddles/strangles)

## 6. Users

- **Primary:** the hackathon judges — need to see a coherent, auditable, real decision lifecycle in a short demo window
- **Secondary:** the builder(s) — need a system that is debuggable within a 4-day, free-tier-quota constrained schedule

## 7. Constraints

- Solo/duo team, limited options trading experience
- 4-day build window
- Free-tier coding agents (rate/quota limited)
- Free-tier LLM APIs only (OpenRouter + Google AI Studio)
- Alpaca paper trading only — no real capital

## 8. Non-Goals

- Proving the strategy is profitable at statistically significant sample size (not achievable in 4 days — the backtest and live demo are evidence of sound process, not a profitability guarantee)
- Building a production-grade trading system — this is a hackathon prototype demonstrating an architecture pattern
