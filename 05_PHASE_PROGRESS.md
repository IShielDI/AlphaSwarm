# AlphaSwarm — Phase Progress Log

**Instructions for the coding agent:** update this file at the end of every work session. Mark each item's status as `[ ]` TODO, `[~]` IN PROGRESS, or `[x]` DONE. Add a one-line note under any item that was changed, blocked, or cut from the original plan — do not silently skip something without noting it here. Do not mark a phase complete until every item in it is `[x]` or explicitly noted as cut.

---

## Day 1 — Deterministic Backbone + Backtest

- [x] Alpaca paper account + API keys configured (`ALPACA_API_KEY`, `ALPACA_SECRET_KEY`)
- [x] MCP server connected and verified (pull option chain, Greeks, IV for ticker universe)
- [x] `schemas/agent_schemas.py` — fixed I/O schemas defined for all agents (do this before Day 2)
- [x] `engine/risk_engine.py` — deterministic checks implemented (max loss, position size, concentration, duplicate-order)
- [x] `engine/execution_service.py` — multi-leg order construction (`order_class: "mleg"`) and submission implemented
- [x] One hand-picked example spread manually submitted and confirmed filled in paper trading, end-to-end
- [x] `backtest/historical_backtest.py` — historical price/IV data pulled for ticker universe, entry rule (direction + IV rank) tested mechanically against recent history
- [x] Backtest result recorded: does the strategy show real edge on historical data? (note the outcome here, even if inconclusive)

**Day 1 notes:**
- Paper account connected ($100,000 equity, $400,000 buying power, 0 positions) via `alphaswarm/data/alpaca_client.py`; keys stored in gitignored `.env`.
- `alphaswarm/data/mcp_client.py` pulls live option chain + Greeks + IV (SPY 260903 call surface returned strikes/IV/delta/gamma/theta/vega/bid/ask). External Node MCP-server binary wiring deferred to Day 2 (agents call this surface).
- `schemas/agent_schemas.py` defines the locked TRD Section 4 schemas exactly + a pure `validate_agent_output` helper (no LLM).
- `engine/risk_engine.py` (no LLM, deterministic) + `tests/test_risk_engine.py` pass (max-loss cap, position-size, concentration, duplicate-order all covered).
- `engine/execution_service.py` builds mleg spreads (bull put / bear call), enforces short-leg-covered + 1:1 ratio before submission; `tests/test_execution_service.py` passes.
- LIVE paper trade FILLED (2026-08-28): SPY bull put 755/750, exp 260908, qty 2 -- long +2 @0.74, short -2 @1.08, net credit ~$68. Ran through RiskEngine (all PASS) then ExecutionService (mleg limit).
- BACKTEST (6 yrs, 2,008 setups): win rate 79.3%, avg +$5.60/spread, mean credit ~$97.6, max loss -$480. Positive in AAPL/AMZN/MSFT/NVDA/IWM; NEGATIVE in QQQ/SPY/TSLA. CAVEATS: historical IV not on free Alpaca feed -> used 20d REALIZED vol as IV proxy (BS-priced credit); 10-day mark-to-model outcome, no costs, naive per-contract sizing (overlapping trades, not portfolio PnL). Verdict: promising gross edge but NOT validated as real profitability -- inconclusive, not a guarantee.

---

## Day 2 — Layer 1 Agents + Strategist

- [ ] `agents/market_agent.py` (DeepSeek via OpenRouter) — returns fixed schema, tested on real data
- [ ] `agents/volatility_agent.py` (DeepSeek via OpenRouter) — returns fixed schema, tested on real data
- [ ] `agents/options_agent.py` (Qwen3-Coder via OpenRouter) — returns fixed schema, tested on real data
- [ ] `agents/portfolio_agent.py` (GLM-4.5-Air via OpenRouter) — returns fixed schema, tested on real data
- [ ] `agents/strategist.py` (Gemini via Google AI Studio) — synthesizes all four outputs into one proposal, considers 1-2 alternatives, can output NO_TRADE
- [ ] Full Layer 1 → Strategist chain tested on 2-3 real market snapshots, outputs sanity-checked by hand

**Day 2 notes:**

---

## Day 3 — Mentor Loop + Risk Engine + Execution Wiring

- [ ] `agents/mentor.py` (Nemotron via OpenRouter) — schema tested standalone against sample proposals BEFORE wiring into the loop
- [ ] Mentor component-by-component audit implemented, producing the fixed `overall_decision` / `imperfections` JSON
- [ ] Targeted correction routing implemented (only responsible agent(s) re-invoked, `invalidate_downstream` respected)
- [ ] Revision loop capped at ONE round, enforced in `orchestrator.py` (not left to the Mentor's own judgment)
- [ ] Mentor APPROVE wired into `engine/risk_engine.py`
- [ ] Risk Engine PASS wired into `engine/execution_service.py` → real Alpaca paper order submitted
- [ ] `monitor/position_monitor.py` — scheduled HOLD/EXIT check implemented
- [ ] One full real decision-to-execution cycle completed live, end-to-end

**Day 3 notes:**

---

## Day 4 — Light Self-Improvement + Demo Assembly

- [ ] `improve/outcome_analyzer.py` — structured post-mortem generated for at least one closed trade
- [ ] `improve/imperfection_log.py` — running per-agent weakness table implemented and populated from available trades
- [ ] `improve/improvement_engine.py` — ONE improvement hypothesis generated from the log
- [ ] Mentor review of that hypothesis implemented (accept/reject), explicitly framed in the demo as a mechanism demo, not a validated claim
- [ ] Dashboard / walkthrough assembled showing one full decision lifecycle
- [ ] Demo recorded or live run rehearsed at least once end-to-end before presenting

**Day 4 notes:**

---

## Cut / Deferred Items (do not build unless time allows after Day 4 core is complete)

- [ ] Multi-strategist layer
- [ ] Full versioning/promotion/rollback pipeline
- [ ] Retrieval-based agent memory
- [ ] Alpaca CLI integration
- [ ] Human approval gate

## Overall Status

**Current phase:** _(update this line each session)_
**Blockers:** _(update this line each session)_
**Confidence in Day-4 demo readiness:** _(update this line each session — Low / Medium / High)_
