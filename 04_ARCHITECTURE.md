# AlphaSwarm — Architecture

## 1. System Flow

```
Alpaca Data (bars + option chain + Greeks/IV, via MCP)
        │
        ▼
┌─────────────────────────────────────────────┐
│              LAYER 1 — RESEARCH              │
│  Market Agent │ Volatility Agent │ Options   │
│                                  │ Agent      │
│              Portfolio Agent                 │
└───────────────────┬───────────────────────────┘
                     ▼
              STRATEGIST
   (synthesizes proposal, considers 1-2
    alternatives, can output NO TRADE)
                     ▼
              MENTOR / JUDGE
  (component-by-component audit; targeted
   correction to the responsible agent;
   CAPPED AT ONE revision round)
                     ▼
              REVISED PROPOSAL → MENTOR
                     ▼
              DETERMINISTIC RISK ENGINE
     (max loss, position size, concentration,
        duplicate-order check — no LLM)
                     ▼
              ALPACA PAPER EXECUTION
        (multi-leg order, order_class="mleg")
                     ▼
              POSITION MONITOR
        (scheduled check → HOLD / EXIT)
                     ▼
         ┌───────────┴───────────┐
         ▼                       ▼
  OUTCOME ANALYZER      IMPERFECTION LOG
  (post-mortem per            (running table of
   closed trade)             per-agent weaknesses)
         │                       │
         └───────────┬───────────┘
                      ▼
          ONE IMPROVEMENT ENGINE PASS
        (hypothesis → Mentor reviews →
          ACCEPT/REJECT — mechanism demo,
             not a validated claim)
```

## 2. Suggested Repo / Module Structure

```
alphaswarm/
├── data/
│   ├── alpaca_client.py        # direct alpaca-py wrapper (Risk Engine, Execution)
│   └── mcp_client.py           # MCP server wrapper (agent data pulls)
├── agents/
│   ├── market_agent.py         # DeepSeek
│   ├── volatility_agent.py     # DeepSeek
│   ├── options_agent.py        # Qwen3-Coder
│   ├── portfolio_agent.py      # GLM-4.5-Air
│   ├── strategist.py           # Gemini
│   └── mentor.py                # Nemotron
├── engine/
│   ├── risk_engine.py          # deterministic, no LLM
│   └── execution_service.py    # order construction + submission
├── monitor/
│   └── position_monitor.py
├── improve/
│   ├── outcome_analyzer.py
│   ├── imperfection_log.py
│   └── improvement_engine.py
├── schemas/
│   └── agent_schemas.py        # fixed I/O schemas, see TRD Section 4
├── backtest/
│   └── historical_backtest.py  # Day 1 deterministic strategy validation
├── decision_store.py           # decision data model, see TRD Section 6
├── orchestrator.py             # runs one full decision cycle end-to-end
└── config.py                   # API keys, ticker universe, thresholds
```

## 3. Component Boundaries

- **`agents/`** — every file here makes exactly one LLM call type, returns the fixed schema for that agent, and does nothing else (no execution, no risk logic).
- **`engine/`** — zero LLM calls. Pure deterministic Python. This is the safety boundary that no agent, including the Mentor, can override.
- **`orchestrator.py`** — the only place that sequences the full flow (Layer 1 → Strategist → Mentor → [correction loop, capped at 1] → Risk Engine → Execution → Monitor). Keep the one-revision-round cap enforced here, not left to the Mentor's own judgment.
- **`decision_store.py`** — every decision cycle writes one record here, regardless of outcome (including NO_TRADE and REJECT cycles) — this is what feeds the Outcome Analyzer and demo narration later.

## 4. Data Flow Notes

- Layer 1 agents run independently (can be called in parallel) — they do not see each other's output.
- The Strategist is the first component to see all four Layer-1 outputs together.
- The Mentor sees the Strategist's full proposal plus the original Layer-1 outputs (needed to audit component-by-component against source data, not just the synthesized proposal).
- Targeted correction: Mentor's `imperfections` list determines exactly which Layer-1 agent(s) get re-invoked. If `invalidate_downstream` is true for a component, downstream components built on it are also recomputed even if the Mentor didn't flag them directly.

## 5. Build-Order Dependency Map

This determines what can be built and tested independently before wiring together (see Phase file for day-by-day sequencing):

1. `data/alpaca_client.py` + `engine/` — testable standalone with a hand-picked trade, no agents needed
2. `schemas/agent_schemas.py` — define before writing any agent, since every agent and the Mentor depend on these being fixed early
3. `agents/market_agent.py`, `volatility_agent.py`, `options_agent.py`, `portfolio_agent.py` — testable independently against real Alpaca data before the Strategist exists
4. `agents/strategist.py` — testable once all four Layer-1 agents produce valid schema output
5. `agents/mentor.py` — testable once the Strategist produces a real proposal to audit
6. `orchestrator.py` — wires everything above together with the one-revision-round cap
7. `monitor/`, `improve/` — built last, depend on the orchestrator producing real executed trades to monitor and analyze
