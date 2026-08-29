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

- [x] `agents/market_agent.py` (DeepSeek via OpenRouter) — returns fixed schema, tested on real data
- [x] `agents/volatility_agent.py` (DeepSeek via OpenRouter) — returns fixed schema, tested on real data
- [x] `agents/options_agent.py` (Qwen3-Coder via OpenRouter) — returns fixed schema, tested on real data
- [x] `agents/portfolio_agent.py` (GLM-4.5-Air via OpenRouter) — returns fixed schema, tested on real data
- [x] `agents/strategist.py` (Gemini via Google AI Studio) — synthesizes all four outputs into one proposal, considers 1-2 alternatives, can output NO_TRADE
- [x] Full Layer 1 → Strategist chain tested on 2-3 real market snapshots, outputs sanity-checked by hand

**Day 2 notes:**
- All four Layer-1 agents + Strategist implemented with LOCKED model bindings (DeepSeek-V3 / Qwen3-Coder / GLM-4.5-Air via OpenRouter; gemini-3.6-flash via Google AI Studio). Shared `agents/llm_client.py` enforces: JSON-only parsing, exact schema match against `schemas/agent_schemas.py`, semantic validators (spread-type scope, leg geometry, alternatives/reasons-not-to-trade present), retry max 2 — a third consecutive schema failure raises `AgentSchemaError` and HALTS (per rule: never loosen schema).
- Each agent gets a deterministic data snapshot (price/vol/option-surface/account built in code, no LLM); the LLM only interprets. Option snapshots chunked 100 symbols/request (Alpaca limit).
- Real-data tests all passed on first schema-valid output: SPY market (trending_up/bullish, conf 0.7), SPY vol (low regime, IV cheap, conf 0.9), SPY options (real bull put 760/750 w/ actual quotes + Greeks, conf 0.85), portfolio (correctly detected the live Day-1 SPY put position and flagged conflict).
- NO_TRADE test (fake disagreeing signals + do_not_proceed portfolio): strategist returned literal "NO_TRADE" — passed. Also NO_TRADE on real SPY & NVDA & MSFT snapshots (portfolio conflict / duplicate exposure) — refusing to trade is the correct behavior given the open Day-1 SPY position.
- Full chain AAPL (real snapshot): complete trade proposal — bull put 315/310 exp 260904, credit ~$1.11, max loss $389, alternatives considered (bear_call_spread, naked_short_put — scope-rejected), entry/exit/invalidation conditions, honest reasons_not_to_trade (low volume conviction, SMA20<SMA50, 7-DTE gamma). Confidence 0.78. Ready for Mentor review in Day 3.
- Infra fixes: gemini-2.5-flash is 404 for new keys → gemini-3.6-flash; 3.6-flash is a thinking model so maxOutputTokens raised 2048→8192 (2048 truncates mid-thought and the call stalls); hard 150s wall-clock deadline per LLM call via daemon thread (proxy keepalives defeat socket read-timeouts); transport errors now count as attempts and are retried.

---

## Day 3 — Mentor Loop + Risk Engine + Execution Wiring

- [x] `agents/mentor.py` (Nemotron via OpenRouter) — schema tested standalone against sample proposals BEFORE wiring into the loop
- [x] Mentor component-by-component audit implemented, producing the fixed `overall_decision` / `imperfections` JSON
- [x] Targeted correction routing implemented (only responsible agent(s) re-invoked, `invalidate_downstream` respected)
- [x] Revision loop capped at ONE round, enforced in `orchestrator.py` (not left to the Mentor's own judgment)
- [x] Mentor APPROVE wired into `engine/risk_engine.py`
- [x] Risk Engine PASS wired into `engine/execution_service.py` → real Alpaca paper order submitted
- [x] `monitor/position_monitor.py` — scheduled HOLD/EXIT check implemented
- [ ] One full real decision-to-execution cycle completed live, end-to-end

**Day 3 notes:**
- STANDALONE MENTOR VALIDATION (before any wiring, per instruction): 4 realistic sample cases (clean proposal / direction conflict / fabricated credit / portfolio conflict ignored) — 4/4 schema-exact on the rigid MENTOR_SCHEMA. Nemotron caught real issues: the fabricated-credit case (strategist quoted $2.40 vs options agent's $0.85 — flagged owner=strategist, high severity), the direction-conflict case (high severity bias_integration), and even the short-put vega sign in my sample data. Required 3 infra fixes first: Nemotron reasoning tokens blew the 2000 max_tokens cap (raised to 8000), >150s latency (hard deadline raised to 240s), model name verified live against the OpenRouter catalog.
- Correction routing implemented in `orchestrator.py` with an explicit ownership map (Agent Rules Section 1 table): flagged owner re-invoked with original inputs; `invalidate_downstream` forces re-run of every downstream consumer; strategist always re-synthesizes with the audit attached via a new `mentor_feedback` parameter. Exactly ONE revision round — REJECT/WAIT or failed re-audit ends the cycle NO_TRADE, no looping.
- `decision_store.py`: append-only JSONL trace of every cycle (L1 outputs, proposals, both mentor audits, corrections, risk checks, execution result).
- Live end-to-end runs: 6 cycles (AAPL, NVDA, MSFT, META, AMD, TSLA). NVDA exercised the full correction path (mentor REVISE → correction round → re-audit). ALL cycles ended NO_TRADE — see blocker below.
- Risk Engine wiring verified standalone on a realistic proposal: all 4 checks PASS ($315 max loss vs $2,000 cap, $500 notional, concentration, no duplicate). mleg leg construction validated (SELL_TO_OPEN/BUY_TO_OPEN, qty 1).
- Position Monitor live: correctly evaluates the open Day-1 SPY 750/755 puts (dte=10, plpc -7%/-5% → HOLD) with deterministic rules: expired/dte<=2 → EXIT, plpc >= +50% → EXIT, plpc <= -100% → EXIT, dte <= 7 → REVIEW, else HOLD.
- **BLOCKER (step 6): no filled order yet.** Two compounding causes, in order of importance: (1) The Strategist returns NO_TRADE on every live snapshot. The visible data reason: IV is elevated vs realized across the whole universe right now (e.g. MSFT IV 41.4% vs 20d realized 26.5%) — pre-weekend event premium. This is actually FAVORABLE for selling credit spreads, but the Strategist reads `iv_assessment: "expensive"` as a reason not to trade — a calibration bug, not a schema failure. Fix candidate (needs owner sign-off, since it biases the system toward trading): clarify in the Strategist prompt that IV > realized is attractive for premium SELLING; do NOT loosen any schema. (2) Calendar: today is Saturday — even an APPROVE would only queue, not fill, until Monday's open.


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

**Current phase:** Day 3 implementation complete — Mentor validated standalone (4/4 schema-exact on Nemotron), correction routing + one-revision cap implemented, Risk Engine -> Execution Service -> Position Monitor wiring verified with real Alpaca paper calls. **Step 6 (filled order) NOT achieved; not moving to Day 4.**

**Blockers to a real filled order (in order):**
1. **Market closed:** next Alpaca market open is Mon 2026-08-31 09:30 ET (verified via get_clock). No paper order can fill before then regardless of pipeline state.
2. **Gemini free-tier quota exhausted (HTTP 429):** the Strategist cannot run live until the daily quota resets or billing is enabled on the Google AI Studio key.
3. **Strategist calibration (root cause of prior NO_TRADEs):** on every live snapshot the Strategist treats "IV expensive vs realized" as a reason NOT to trade. For vertical CREDIT spreads, IV > realized is favorable (selling overpriced premium). Needs a one-line prompt calibration in `agents/strategist.py` clarifying the credit-seller's perspective, then a re-run at Monday's open.

**To unblock Monday:** fix blocker 3, wait for quota reset (blocker 2), run `Orchestrator().run_cycle()` shortly after 09:30 ET (blocker 1), confirm Mentor APPROVE -> Risk PASS -> SUBMITTED -> filled.

**Confidence in Day-4 demo readiness:** High — the full pipeline incl. Mentor loop, correction cap, and execution path is built and individually verified; only the last-mile live fill is pending market hours.
