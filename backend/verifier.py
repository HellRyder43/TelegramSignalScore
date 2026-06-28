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


def _points(direction: str, entry: float, level: float) -> float:
    """Signed points from entry to level. Positive when profitable."""
    if direction == "BUY":
        return (level - entry) / POINT_SIZE
    return (entry - level) / POINT_SIZE


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
    max_candles = VERIFICATION_WINDOW_HOURS * 60  # 2880 for 48 h

    # Normalise posted_at to a naive UTC datetime.
    # Supabase returns ISO strings ("2024-01-15T02:00:00+00:00"); MT5's C extension
    # expects a datetime object and treats it as UTC. Passing a tz-aware object
    # can cause TypeErrors on Windows, so we strip tzinfo after converting to UTC.
    if isinstance(posted_at, str):
        posted_at = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    if posted_at.tzinfo is not None:
        posted_at = posted_at.astimezone(timezone.utc).replace(tzinfo=None)

    if not mt5.initialize():
        raise MT5NotConnectedError(str(mt5.last_error()))

    rates = mt5.copy_rates_from(sym, mt5.TIMEFRAME_M1, posted_at, max_candles)
    if rates is None or len(rates) == 0:
        raise MT5NotConnectedError(
            f"copy_rates_from returned no data for {sym} from {posted_at}"
        )

    # Phase 1: find entry fill
    fill_idx: int | None = None
    for i, candle in enumerate(rates):
        if direction == "BUY" and candle["low"] <= entry:
            fill_idx = i
            break
        if direction == "SELL" and candle["high"] >= entry:
            fill_idx = i
            break

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
