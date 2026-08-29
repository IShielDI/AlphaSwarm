"""AlphaSwarm configuration.

Central place for secrets, the ticker universe, and fixed thresholds.

Environment/secrets (see TRD Section 8):
    ALPACA_API_KEY          - Alpaca paper trading API key
    ALPACA_SECRET_KEY       - Alpaca paper trading secret key
    OPENROUTER_API_KEY      - OpenRouter provider key
    GOOGLE_AI_STUDIO_API_KEY- Google AI Studio provider key (Strategist/Gemini)

The values below are empty placeholders. Set them either via environment
variables or by filling in the placeholders directly. Never commit real keys.
"""

import os

from dotenv import load_dotenv

# Load secrets from a local .env file if present (never commit .env).
load_dotenv()

# ---------------------------------------------------------------------------
# Secrets (placeholders — load from environment/.env, fall back to placeholder)
# ---------------------------------------------------------------------------
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "<YOUR_ALPACA_API_KEY>")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "<YOUR_ALPACA_SECRET_KEY>")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "<YOUR_OPENROUTER_API_KEY>")
GOOGLE_AI_STUDIO_API_KEY = os.environ.get(
    "GOOGLE_AI_STUDIO_API_KEY", "<YOUR_GOOGLE_AI_STUDIO_API_KEY>"
)

# Alpaca paper trading endpoint (never real capital).
ALPACA_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_BASE_URL = "https://data.alpaca.markets"

# ---------------------------------------------------------------------------
# Ticker universe (PRD Section 4): 5-8 liquid large-cap/ETF tickers.
# Selected for deep options liquidity (SPY/QQQ/IWM + megacap single names).
# ---------------------------------------------------------------------------
TICKER_UNIVERSE = [
    "SPY",   # S&P 500 ETF — deepest options liquidity
    "QQQ",   # Nasdaq-100 ETF
    "IWM",   # Russell 2000 ETF
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "NVDA",  # NVIDIA
    "TSLA",  # Tesla
    "AMZN",  # Amazon
]

# ---------------------------------------------------------------------------
# Mentor revision cap (Agent Rules Section 3.3 / TRD Section 7).
# The Mentor correction loop is capped at ONE revision round. If the revised
# proposal still fails Mentor audit, the decision defaults to NO TRADE / REJECT.
# The cap is enforced here and in orchestrator.py — never an open-ended loop.
# ---------------------------------------------------------------------------
MAX_REVISION_ROUNDS = 1

# ---------------------------------------------------------------------------
# Strategy-scope guardrails (for future deterministic components; placeholders).
# ---------------------------------------------------------------------------
# Vertical credit spreads only (bull put / bear call) — PRD Section 5.
ALLOWED_STRUCTURES = ["bull_put_spread", "bear_call_spread"]

# Swing horizon: 7-21 DTE entries, closed before expiration (PRD Section 4).
MIN_DTE = 7
MAX_DTE = 21

# ---------------------------------------------------------------------------
# Risk Engine thresholds (deterministic, no LLM) -- see engine/risk_engine.py.
# All percentages are fractions of 1.0.
# ---------------------------------------------------------------------------
# Max allowable max-loss on a single trade, as a fraction of account equity.
MAX_LOSS_PER_TRADE_PCT = 0.02          # 2% of equity

# Cap on the option premium notional exposed per trade (as fraction of equity).
MAX_PREMIUM_NOTIONAL_PCT = 0.05        # 5% of equity

# Max fraction of account equity that may be *at risk* in a single underlying.
MAX_CONCENTRATION_PER_UNDERLYING_PCT = 0.25

# Hard cap on contracts for one spread leg (sanity guard).
MAX_CONTRACTS_PER_LEG = 100

# ---------------------------------------------------------------------------
# Optional human approval gate (Phase 5.1). Default OFF -- the hackathon
# requires autonomous execution as the primary mode; this gate is an optional,
# demonstrable safety layer, not a replacement for autonomy. When True, the
# orchestrator pauses AFTER the Risk Engine passes and asks a human to approve
# the order before submitting it. The gate is an additional SOFT checkpoint
# layered after the Risk Engine -- it is never a bypass of, or substitute for,
# the deterministic Risk Engine boundary.
# ---------------------------------------------------------------------------
HUMAN_GATE = False

# ---------------------------------------------------------------------------
# Dual Strategist parallel synthesis & arbitration (default OFF).
# When True, runs a primary and conservative strategist in parallel,
# arbitrating agreement before feeding the Mentor.
# ---------------------------------------------------------------------------
ENABLE_DUAL_STRATEGIST = False

