# AlphaSwarm — Technical Requirements Document (TRD)

## 1. Tech Stack

- **Language:** Python
- **Trading SDK:** `alpaca-py` (official Alpaca Python SDK) for direct execution/Risk Engine calls
- **Agent data access:** Alpaca Trading MCP Server for LLM-agent-driven pulls of option chains, Greeks, IV
- **LLM access:** two providers, one API key each
  - **OpenRouter** — DeepSeek, Qwen3-Coder, GLM-4.5-Air, Nemotron (swap `model` parameter per agent, one integration)
  - **Google AI Studio** — Gemini Flash (Strategist only)
- **Environment:** Alpaca paper trading account ($100,000 provided)

## 2. Alpaca Integration Details

### 2.1 Options trading access
- Level 3 (multi-leg) options trading is enabled by default in Alpaca's paper environment — no application/approval step needed. (This requirement applies to live trading only.)

### 2.2 Order construction
- All spread trades use `order_class: "mleg"` with a `legs` array.
- Each leg specifies: symbol, side, ratio quantity, position intent (`buy_to_open` / `sell_to_open`).
- The full spread fills as a single atomic order — never construct two separate single-leg orders for one spread.
- **Hard constraint:** every short leg must be covered by a long leg within the same order, or Alpaca rejects it. Vertical credit spreads satisfy this by construction — verify this holds for every proposal before submission.

### 2.3 Split between MCP and direct SDK
- **Direct `alpaca-py` calls:** Risk Engine and execution/order-submission layer (deterministic, no LLM involved).
- **MCP Server:** all Layer-1 agent data pulls (option chain, Greeks, IV, historical bars) that feed the Market/Volatility/Options/Portfolio agents.

## 3. Data Requirements

- Historical price + implied volatility data for the ticker universe (Alpaca Market Data API), for the Day 1 deterministic backtest.
- Real-time/near-real-time option chain, Greeks, and IV for the ticker universe during live agent runs (via MCP).
- Current account state (positions, buying power, existing exposure) for the Portfolio Agent and Risk Engine.

## 4. Agent I/O Schemas

Each Layer-1 agent must return a fixed, structured (JSON) output — this is a hard requirement, not a suggestion, since the Mentor's audit and the Strategist's synthesis both depend on parseable, consistent fields.

**Market Agent output:**
```
market_regime, directional_bias, confidence, supporting_evidence,
contradictory_evidence, risk_factors
```

**Volatility Agent output:**
```
volatility_regime, iv_assessment, realized_vol_assessment,
term_structure_assessment, confidence, evidence, warnings
```

**Options Agent output:**
```
candidate_structures, contract_candidates, structure_rationale,
greeks, liquidity_assessment, payoff_profile, risks, confidence
```

**Portfolio Agent output:**
```
current_exposure, portfolio_impact, concentration_risk,
correlation_risk, conflicts, recommendation
```

**Strategist output:** structured trade proposal containing underlying, market thesis, volatility thesis, selected structure, contract, rationale, alternative structures considered, entry/exit/invalidation conditions, portfolio impact, max loss, key risks, confidence, reasons NOT to trade, OR an explicit `NO_TRADE` value.

**Mentor output (must be strict, machine-readable JSON):**
```json
{
  "overall_decision": "APPROVE | REVISE | REJECT | WAIT",
  "imperfections": [
    {
      "component": "string",
      "owner": "agent_name",
      "severity": "low | medium | high",
      "reason": "string",
      "action": "string",
      "invalidate_downstream": true | false
    }
  ]
}
```
This schema is the single highest-risk point of failure in the system — the targeted-correction mechanism cannot function if this JSON is malformed. Test the assigned model (Nemotron) against this exact schema on sample proposals before wiring it into the loop.

## 5. Deterministic Components (No LLM)

- **Risk Engine:** validates max loss, position size limit, portfolio concentration, duplicate-order prevention. Hard-coded rules, not a prompt. Must run and produce PASS/FAIL before any Alpaca order is submitted.
- **Execution Service:** constructs and submits the multi-leg order via `alpaca-py`, tracks order status, reconciles resulting position.
- **Position Monitor:** scheduled check against open positions (P&L, Greeks, time-to-expiration, invalidation conditions) — outputs HOLD/REDUCE/EXIT/REVIEW. Any actual exit re-enters the Risk Engine/Execution Service before submission.

## 6. Decision Data Model

Every decision cycle should be logged in a structured record for debugging, demo narration, and the Outcome Analyzer:
```
decision_id, timestamp, market_analysis, volatility_analysis,
options_analysis, portfolio_analysis, strategist_proposal,
mentor_audit, mentor_feedback, revision_history, risk_check,
execution_result, position_state, outcome, agent_errors
```

## 7. Non-Functional Requirements

- **Mentor correction loop:** hard-capped at ONE revision round. Do not implement open-ended looping.
- **Rate limits:** OpenRouter free tier (~50-1,000 req/day depending on credit top-up) and Google AI Studio free tier (~500-1,500 req/day) must not be exceeded during testing — batch test runs rather than continuous polling during development.
- **Failure handling:** any malformed agent JSON output should be caught and logged, not silently passed downstream — the pipeline should fail loudly rather than let a bad schema propagate into the Risk Engine.
- **No fine-tuning / weight training** of any model — out of scope entirely for this build.

## 8. Environment / Secrets

- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` (paper trading)
- `OPENROUTER_API_KEY`
- `GOOGLE_AI_STUDIO_API_KEY`
