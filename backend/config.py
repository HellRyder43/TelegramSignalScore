"""
All tunable constants for the XAUUSD Signal Trust Score system.
Edit values here; never hard-code them in pipeline modules.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── MT5 / Price ──────────────────────────────────────────────────────────────

# Exact symbol name in your MT5 terminal (e.g. "XAUUSD.r" or "XAUUSD")
MT5_SYMBOL: str = os.getenv("MT5_SYMBOL", "XAUUSD")

# How long after a signal is posted to keep trying to resolve it (hours)
VERIFICATION_WINDOW_HOURS: int = 48

# 1 point = $1.00 price movement on XAUUSD.
# Convention: retail gold traders say "50 pips" to mean a $50 price move.
# With 0.01 lot (1 oz), a 50-point move = $50 profit/loss.
# Dashboard and scoring display points in this unit (e.g. SL of 45 pts, TP of 65 pts).
POINT_SIZE: float = 1.0

# MT5 scheduled re-check interval (seconds) for unresolved signals
VERIFY_INTERVAL_SECS: int = int(os.getenv("VERIFY_INTERVAL_SECS", "300"))

# Default take-profit distance (points) used when a channel posts no explicit TP.
# Signals are considered won when price moves this many points in the signal's direction.
# Set to 50 to match the user's personal minimum profit target.
DEFAULT_TP_PIPS: int = 50

# ─── Trust Score Weights ──────────────────────────────────────────────────────
# Components sum to 100 at maximum. Weights are maximums for each component.

# Performance components (max total: 75 before sample-size dampening)
WEIGHT_WIN_RATE: float = 40.0       # 0–40 based on verified win rate
WEIGHT_RR: float = 25.0             # 0–25 based on average R:R
WEIGHT_EXPECTANCY: float = 20.0     # 0–20 based on avg points per trade

# Integrity component (starts at max and penalties reduce it)
WEIGHT_INTEGRITY: float = 25.0      # 0–25; penalties subtract from this

# ─── Sample-size Dampener ─────────────────────────────────────────────────────
# Multiplier applied to raw performance score (0.0–1.0).
# With fewer than MIN_SIGNALS_FULL_WEIGHT signals, the score is dampened.
MIN_SIGNALS_FULL_WEIGHT: int = 30   # at or above this, multiplier = 1.0
MIN_SIGNALS_FLOOR: int = 3          # below this, multiplier = 0.0 (no score)

# ─── Integrity Penalties ─────────────────────────────────────────────────────
# Each event subtracts from the integrity component (floored at 0).
PENALTY_POST_MOVE_EDIT: float = 3.0       # per post-move level edit
PENALTY_DELETED_SIGNAL: float = 2.0       # per deleted forward signal
PENALTY_CONTRADICTED_SCREENSHOT: float = 5.0  # per fabricated screenshot claim

# ─── Backfill / Zone Weighting ────────────────────────────────────────────────
# Signals from these sources are counted at a reduced weight in performance components.
BACKFILL_SIGNAL_WEIGHT: float = 0.7   # backfilled messages (history before live)
ZONE_SIGNAL_WEIGHT: float = 0.8       # zone-estimated signals (image-derived levels)

# ─── Verdict Thresholds ───────────────────────────────────────────────────────
# Map final Trust Score (0–100) to a plain-language verdict.
# Scores below the first threshold → avoid; above the last → trusted.
VERDICT_THRESHOLDS: dict[str, int] = {
    "avoid":   0,    # score < 25
    "observe": 25,   # 25 ≤ score < 45
    "caution": 45,   # 45 ≤ score < 65
    "trusted": 65,   # score ≥ 65
}

def score_to_verdict(score: int) -> str:
    if score >= VERDICT_THRESHOLDS["trusted"]:
        return "trusted"
    if score >= VERDICT_THRESHOLDS["caution"]:
        return "caution"
    if score >= VERDICT_THRESHOLDS["observe"]:
        return "observe"
    return "avoid"

# ─── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ─── Discord ──────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID: int = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

# ─── Anthropic (Phase 7) ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = "claude-sonnet-4-6"
