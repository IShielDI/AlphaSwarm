# AlphaSwarm — Agent Rules

## 1. Core Ownership Rule

Each agent owns its domain exclusively. No agent should reason outside its assigned responsibility, and no other agent or component should silently override another agent's domain without going through the Mentor's targeted-correction mechanism.

| Agent | Owns |
|---|---|
| Market Agent | Market analysis (trend, regime, directional bias) |
| Volatility Agent | Volatility analysis (IV, realized vol, term structure) |
| Options Agent | Contract/structure analysis (candidates, Greeks, liquidity) |
| Portfolio Agent | Portfolio context (exposure, concentration, conflicts) |
| Strategist | Synthesis into one trade proposal |
| Mentor | Criticism, audit, and targeted feedback routing |
| Risk Engine | Hard deterministic constraints (not owned by any LLM) |
| Execution Service | Order construction and submission |
| Position Monitor | Post-execution position tracking |
| Outcome Analyzer | Post-trade diagnosis |
| Improvement Engine | Candidate process improvements |
| Mentor (2nd role) | Validation of proposed improvements |

This ownership model is what makes the system auditable — every output has exactly one responsible owner, so the Mentor always knows exactly who to send a correction to.

## 2. Model Assignment (Locked)

| Agent | Model | Provider | Reason |
|---|---|---|---|
| Market Agent | DeepSeek (V4 Flash / R1) | OpenRouter | Strong general reasoning over ambiguous signals |
| Volatility Agent | DeepSeek (V4 Flash / R1) | OpenRouter | Quantitative/logic-heavy job |
| Options Agent | Qwen3-Coder | OpenRouter | Reliable structured/tool-use output — most rigid schema of the four |
| Portfolio Agent | GLM-4.5-Air | OpenRouter | Comparatively mechanical — lower model tier is sufficient |
| Strategist | Gemini Flash | Google AI Studio | Needs large context to hold 4 agents' outputs without losing disagreement |
| Mentor | Nemotron | OpenRouter | Highest-stakes structured-output requirement in the system |
| Outcome Analyzer / Improvement Engine | GLM-4.5-Air | OpenRouter | Lower-stakes, infrequent calls |

Do not swap models without re-validating the affected agent's structured-output reliability against its schema.

## 3. Hard Rules (Never Violate)

1. **No agent executes trades directly.** Only the Execution Service, gated by the Risk Engine, submits orders to Alpaca.
2. **The Strategist must be able to output NO TRADE.** A trade must never be generated merely because the pipeline ran — absence of a qualifying setup is a valid, expected outcome.
3. **The Mentor loop is capped at ONE revision round.** If the proposal does not pass Mentor audit after one correction cycle, the decision defaults to NO TRADE / REJECT — it does not loop indefinitely.
4. **The Mentor sends corrections only to the responsible agent(s)**, identified per-component, not a blanket "redo everything" instruction. Use the `invalidate_downstream` flag to determine whether dependent components must also be reconsidered (e.g., a wrong market regime call invalidates the volatility interpretation and options structure built on top of it).
5. **The Risk Engine is deterministic code, never an LLM call.** No agent, including the Mentor, can override a Risk Engine FAIL.
6. **Every Layer-1 agent output must conform to its fixed schema (see TRD Section 4).** Malformed output is a build error to fix, not something to route around.
7. **Options structures are limited to vertical credit spreads only** (bull put / bear call) for this build. The Options Agent should not propose naked options, iron condors, or straddles/strangles regardless of what the data suggests — that is out of scope, not a judgment call for the agent to make.
8. **No fine-tuning, weight updates, or reinforcement learning of any model.** "Improvement" in this system means process/prompt-level changes reviewed by the Mentor, never model retraining.

## 4. Prompting Guidance Per Agent

- **Layer-1 agents (Market/Volatility/Options/Portfolio):** prompts should require the exact output schema every time, with explicit instruction to omit reasoning outside their owned domain. Keep these prompts narrow and specific — resist the temptation to ask one agent to also comment on another's domain.
- **Strategist:** prompt must explicitly require considering at least one alternative structure and explicitly permit NO_TRADE as a valid final answer, not just an edge case.
- **Mentor:** prompt must require decomposition into individual components (see PRD Section 3, step 4) before rendering an overall_decision — do not allow a holistic "looks fine" or "looks bad" judgment without the component breakdown.

## 5. Escalation / Failure Behavior

- If any agent's output fails schema validation twice in a row during a live run, halt that decision cycle and log it — do not proceed to the Strategist/Mentor/Risk Engine with malformed input.
- If the Mentor's overall_decision is REJECT or WAIT, the cycle ends at NO TRADE — it does not retry within the same cycle.
