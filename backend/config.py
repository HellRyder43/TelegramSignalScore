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

# Reject signals whose entry is implausibly far from the market price during the
# verification window — e.g. a pip-count like "300" misparsed as a price while gold
# trades ~4000. Such entries are treated as unverifiable, not real forward signals,
# which stops them poisoning the points/outcome record.
MAX_ENTRY_GAP_POINTS: float = float(os.getenv("MAX_ENTRY_GAP_POINTS", "500"))

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

# ─── Synthetic time-horizon exit ──────────────────────────────────────────────
# Fallback for signals that state NO stop-loss at all (e.g. "BUY @ 4060 TP open").
# Without an exit there is no natural win/loss, so once the entry fills we measure
# the position's P/L a fixed number of minutes later: profit → win, otherwise loss.
# This is symmetric (it can land as a loss just as easily as a win), unlike a
# TP-only check which could only ever win. Such outcomes are ESTIMATES: they are
# tagged method='synthetic_horizon' and counted at a reduced weight in scoring.
SYNTHETIC_EXIT_ENABLED: bool = os.getenv("SYNTHETIC_EXIT_ENABLED", "true").lower() == "true"
SYNTHETIC_EXIT_MINUTES: int = int(os.getenv("SYNTHETIC_EXIT_MINUTES", "10"))
# Performance weight of a synthetic-exit outcome (like BACKFILL/ZONE weights).
SYNTHETIC_SIGNAL_WEIGHT: float = float(os.getenv("SYNTHETIC_SIGNAL_WEIGHT", "0.4"))

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

# ─── Telegram ─────────────────────────────────────────────────────────────────
TG_API_ID: int = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH: str = os.getenv("TG_API_HASH", "")

# Filename for the Telethon session (stored as <name>.session — gitignored)
TG_SESSION_NAME: str = os.getenv("TG_SESSION_NAME", "xau_signal_bot")

# Separate Telethon session for the backfill script. Telethon cannot share one
# session file across two running processes, so backfill must not reuse the live
# ingestor's session. Its own session lets it run concurrently with the listener.
TG_BACKFILL_SESSION_NAME: str = os.getenv(
    "TG_BACKFILL_SESSION_NAME", f"{TG_SESSION_NAME}_backfill"
)

# Comma-separated Telegram channel IDs to monitor.
# Run `python scripts/list_channels.py` once to find your channel IDs.
# Example: TRACKED_CHANNEL_IDS=-1001234567890,-1009876543210
TRACKED_CHANNEL_IDS: list[int] = [
    int(x.strip()) for x in os.getenv("TRACKED_CHANNEL_IDS", "").split(",")
    if x.strip()
]

# ─── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY: str = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

# ─── Discord ──────────────────────────────────────────────────────────────────
DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID: int = int(os.getenv("DISCORD_CHANNEL_ID", "0"))

# ─── MT5 broker server timezone ───────────────────────────────────────────────
# MT5 profit screenshots display times in the broker's server timezone, NOT UTC.
# The screenshot cross-checker uses this to convert those times to UTC correctly.
#
# RoboForex uses EET (Eastern European Time):
#   - UTC+2 in winter  (last Sunday October  → last Sunday March)
#   - UTC+3 in summer  (last Sunday March    → last Sunday October)
#
# "Europe/Riga" covers EET/EEST automatically — DST is handled for you.
# To verify: in MT5 look at the "Server" clock in the bottom status bar.
# Compare it to UTC (worldtimeserver.com). The offset is your broker's offset.
#
# Common alternatives:
#   "Etc/UTC"          — broker uses UTC (rare but some ECN brokers do)
#   "America/New_York" — broker uses EST/EDT (some US-based brokers)
MT5_SERVER_TIMEZONE: str = os.getenv("MT5_SERVER_TIMEZONE", "Europe/Riga")

# ─── Anthropic (Phase 7) ──────────────────────────────────────────────────────
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL: str = "claude-sonnet-4-6"

# ─── AI Intelligence Feature Flags (Phase 8) ─────────────────────────────────
# Set any to "false" in .env to disable that feature while keeping the API key.
AI_PARSER_ENABLED: bool = os.getenv("AI_PARSER_ENABLED", "true").lower() == "true"
AI_QUALITY_ENABLED: bool = os.getenv("AI_QUALITY_ENABLED", "true").lower() == "true"
AI_EDIT_ANALYSIS_ENABLED: bool = os.getenv("AI_EDIT_ANALYSIS_ENABLED", "true").lower() == "true"
AI_CHANNEL_ANALYSIS_ENABLED: bool = os.getenv("AI_CHANNEL_ANALYSIS_ENABLED", "true").lower() == "true"

# ─── AI Quality Weighting ─────────────────────────────────────────────────────
# Signals with quality_score below this are downweighted in performance components.
AI_LOW_QUALITY_THRESHOLD: float = float(os.getenv("AI_LOW_QUALITY_THRESHOLD", "0.4"))
# Weight multiplier for sub-threshold signals (0.5 = half weight in win rate/expectancy).
AI_LOW_QUALITY_WEIGHT: float = float(os.getenv("AI_LOW_QUALITY_WEIGHT", "0.5"))

# ─── AI Edit Penalty ─────────────────────────────────────────────────────────
# Per-edit integrity penalty = ai_suspicion_score × PENALTY_AI_SUSPICIOUS_EDIT.
# At suspicion_score=1.0 this is 5.0 pts; at 0.0 (innocent typo) it is 0.0.
# Falls back to flat PENALTY_POST_MOVE_EDIT (3.0) for edits without AI analysis.
PENALTY_AI_SUSPICIOUS_EDIT: float = float(os.getenv("PENALTY_AI_SUSPICIOUS_EDIT", "5.0"))

# ─── AI Channel Behavior Penalty ─────────────────────────────────────────────
# fraud_risk_score × AI_BEHAVIOR_PENALTY_MAX = integrity deduction, capped at max.
AI_BEHAVIOR_PENALTY_MAX: float = float(os.getenv("AI_BEHAVIOR_PENALTY_MAX", "10.0"))
# Minimum resolved signals before channel behavior analysis runs.
AI_CHANNEL_ANALYSIS_MIN_SIGNALS: int = int(
    os.getenv("AI_CHANNEL_ANALYSIS_MIN_SIGNALS", str(MIN_SIGNALS_FLOOR))
)
# Minimum seconds between *automatic* re-assessments of the same channel, so the
# 5-minute verification loop can't repeatedly re-bill Claude for one channel.
# Manual /ai/assess/channel calls bypass this (force=True).
AI_CHANNEL_ANALYSIS_MIN_INTERVAL_SECS: int = int(
    os.getenv("AI_CHANNEL_ANALYSIS_MIN_INTERVAL_SECS", "3600")
)
