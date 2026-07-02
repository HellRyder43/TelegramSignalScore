"""
MT5 price verifier — Phase 3 implementation.

Connects to the local MT5 terminal, fetches 1-minute candles, and determines
the real outcome of a signal by first-touch logic (SL vs TP).
"""

from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

import MetaTrader5 as mt5

from backend.config import (
    MT5_SYMBOL,
    VERIFICATION_WINDOW_HOURS,
    POINT_SIZE,
    DEFAULT_TP_PIPS,
    SYNTHETIC_EXIT_MINUTES,
    MAX_ENTRY_GAP_POINTS,
)


OutcomeType = Literal["win", "loss", "ambiguous_loss", "unresolved"]


class MT5NotConnectedError(Exception):
    """Raised when MT5 is not running or not logged in."""


class EntryNeverFilledError(Exception):
    """Raised when price never reached the signal's entry level."""


@dataclass
class VerificationResult:
    outcome: OutcomeType
    points: float | None
    candles_walked: int
    is_ambiguous: bool
    notes: str | None
    method: str = "first_touch"   # "first_touch" | "synthetic_horizon"


def _points(direction: str, entry: float, level: float) -> float:
    """Signed points from entry to level. Positive when profitable."""
    if direction == "BUY":
        return (level - entry) / POINT_SIZE
    return (entry - level) / POINT_SIZE


def _prepare_posted_at(posted_at: datetime | str) -> datetime:
    """Normalise posted_at to a naive UTC datetime for MT5's C extension.

    Supabase returns ISO strings; MT5 expects a datetime treated as UTC. Passing
    a tz-aware object can raise TypeErrors on Windows, so strip tzinfo after
    converting to UTC.
    """
    if isinstance(posted_at, str):
        posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    if posted_at.tzinfo is not None:
        posted_at = posted_at.astimezone(timezone.utc).replace(tzinfo=None)
    return posted_at


def _load_m1_rates(sym: str, posted_at: datetime):
    """Connect to MT5 and fetch the verification window of M1 candles."""
    if not mt5.initialize():
        raise MT5NotConnectedError(str(mt5.last_error()))
    max_candles = VERIFICATION_WINDOW_HOURS * 60  # 2880 for 48 h
    rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, posted_at, max_candles)
    if rates is None or len(rates) == 0:
        raise MT5NotConnectedError(
            f"copy_rates_from returned no data for {sym} from {posted_at}"
        )
    return rates


def _find_entry_fill(rates, direction: str, entry: float) -> int | None:
    """Index of the first candle whose range reaches the entry price, or None."""
    for i, candle in enumerate(rates):
        if direction == "BUY" and candle["low"] <= entry:
            return i
        if direction == "SELL" and candle["high"] >= entry:
            return i
    return None


def _assert_plausible_entry(entry: float, rates) -> None:
    """Guard against pip-counts misparsed as prices (e.g. entry 300 vs gold ~4000).

    A real forward entry sits within — or just outside — the price actually traded
    in the window. An entry far outside that band would otherwise "fill" spuriously
    (a SELL at 100 fills instantly against a 4000 market) and record a nonsense P/L.
    Treated as never-filled so it stays unverified rather than poisoning the record.
    """
    lo = min(c["low"] for c in rates)
    hi = max(c["high"] for c in rates)
    if entry < lo - MAX_ENTRY_GAP_POINTS or entry > hi + MAX_ENTRY_GAP_POINTS:
        raise EntryNeverFilledError(
            f"Entry {entry} implausible vs window range [{lo:.1f}, {hi:.1f}] "
            f"(>{MAX_ENTRY_GAP_POINTS} pts outside) — not a real forward entry."
        )


def verify_signal(
    direction: str,
    entry: float,
    stop_loss: float,
    take_profit: float | None,
    posted_at: datetime | str,
    *,
    symbol: str | None = None,
) -> VerificationResult:
    """
    Verify a forward signal against MT5 1-minute candle data.

    Raises MT5NotConnectedError if MT5 is unavailable.
    Raises EntryNeverFilledError if entry was never reached within the window.

    When take_profit is None, a default of DEFAULT_TP_PIPS points from entry
    is used (configurable in config.py).

    Algorithm:
    1. Walk candles from posted_at to find entry fill.
    2. From fill candle onward, check each candle for first touch of SL or TP.
    3. If both touched in one candle → ambiguous_loss (conservative).
    4. If window exhausted → unresolved.
    """
    direction = direction.upper()
    sym = symbol or MT5_SYMBOL

    if take_profit is None:
        take_profit = (
            entry + DEFAULT_TP_PIPS if direction == "BUY" else entry - DEFAULT_TP_PIPS
        )
    posted_at = _prepare_posted_at(posted_at)
    rates = _load_m1_rates(sym, posted_at)
    _assert_plausible_entry(entry, rates)

    # Phase 1: find entry fill
    fill_idx = _find_entry_fill(rates, direction, entry)
    if fill_idx is None:
        raise EntryNeverFilledError(
            f"Entry {entry} never reached in {len(rates)} candles after {posted_at}"
        )

    # Phase 2: first-touch resolution starting from fill candle
    for i in range(fill_idx, len(rates)):
        candle = rates[i]
        candles_walked = i + 1

        if direction == "BUY":
            hit_tp = candle["high"] >= take_profit
            hit_sl = candle["low"] <= stop_loss
        else:
            hit_tp = candle["low"] <= take_profit
            hit_sl = candle["high"] >= stop_loss

        if hit_tp and hit_sl:
            return VerificationResult(
                outcome="ambiguous_loss",
                points=_points(direction, entry, stop_loss),
                candles_walked=candles_walked,
                is_ambiguous=True,
                notes="Single candle spanned both SL and TP; resolved conservatively as loss.",
            )
        if hit_tp:
            return VerificationResult(
                outcome="win",
                points=_points(direction, entry, take_profit),
                candles_walked=candles_walked,
                is_ambiguous=False,
                notes=None,
            )
        if hit_sl:
            return VerificationResult(
                outcome="loss",
                points=_points(direction, entry, stop_loss),
                candles_walked=candles_walked,
                is_ambiguous=False,
                notes=None,
            )

    return VerificationResult(
        outcome="unresolved",
        points=None,
        candles_walked=len(rates),
        is_ambiguous=False,
        notes=f"Verification window ({VERIFICATION_WINDOW_HOURS}h) expired without SL or TP hit.",
    )


def verify_signal_synthetic(
    direction: str,
    entry: float,
    posted_at: datetime | str,
    *,
    horizon_minutes: int | None = None,
    symbol: str | None = None,
) -> VerificationResult:
    """
    Fallback verification for signals that state NO stop-loss (e.g. "BUY @ 4060
    TP open"). There is no natural exit, so we impose a fixed time-horizon:

    1. Walk candles from posted_at to find the entry fill.
    2. Advance `horizon_minutes` M1 candles from the fill.
    3. Compare that candle's close to entry — profit → win, otherwise loss.

    The outcome is an ESTIMATE (method="synthetic_horizon"). It is symmetric — it
    can land as a loss just as easily as a win — so unlike a TP-only check it does
    not bias a channel's record. Scoring counts it at a reduced weight.

    Raises MT5NotConnectedError / EntryNeverFilledError like verify_signal.
    Returns an "unresolved" result if the horizon hasn't elapsed in the data yet.
    """
    direction = direction.upper()
    sym = symbol or MT5_SYMBOL
    horizon = horizon_minutes or SYNTHETIC_EXIT_MINUTES

    posted_at = _prepare_posted_at(posted_at)
    rates = _load_m1_rates(sym, posted_at)
    _assert_plausible_entry(entry, rates)

    fill_idx = _find_entry_fill(rates, direction, entry)
    if fill_idx is None:
        raise EntryNeverFilledError(
            f"Entry {entry} never reached in {len(rates)} candles after {posted_at}"
        )

    horizon_idx = fill_idx + horizon
    if horizon_idx >= len(rates):
        return VerificationResult(
            outcome="unresolved",
            points=None,
            candles_walked=len(rates),
            is_ambiguous=False,
            notes=f"Synthetic {horizon}m exit: horizon not yet elapsed in available data.",
            method="synthetic_horizon",
        )

    exit_close = float(rates[horizon_idx]["close"])
    points = _points(direction, entry, exit_close)
    outcome: OutcomeType = "win" if points > 0 else "loss"
    return VerificationResult(
        outcome=outcome,
        points=points,
        candles_walked=horizon_idx + 1,
        is_ambiguous=False,
        notes=(
            f"No stop-loss stated — synthetic {horizon}m time-exit. "
            f"P/L {points:+.1f} pts at {horizon}m after fill → {outcome} (estimated)."
        ),
        method="synthetic_horizon",
    )
