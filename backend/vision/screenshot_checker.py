"""
Screenshot cross-checker — Phase 7.

Pulls MT5 M1 candles for the period claimed in a profit screenshot and checks
whether the stated open/close prices were actually traded at the claimed times.

verdicts:
  confirmed     — price reached both claimed open and close levels near the claimed times
  contradicted  — claimed open price was never traded in that window (likely fabricated)
  unverifiable  — MT5 unavailable, incomplete claim data, or period outside history
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.config import MT5_SYMBOL, MT5_SERVER_TIMEZONE
from backend.vision.screenshot_parser import ScreenshotData

logger = logging.getLogger(__name__)

# How close a candle's time must be to the claimed trade time (±minutes)
_TIME_WINDOW_MIN = 20
# Price tolerance: a candle's high/low must be within this of the claimed price
_PRICE_TOLERANCE = 1.00   # $1 tolerance on XAUUSD


def _parse_dt(ts: str) -> datetime | None:
    """Parse an MT5 broker-time string → UTC-aware datetime, or None.

    MT5 profit screenshots display times in the broker's server timezone
    (RoboForex = EET, "Europe/Riga" = UTC+2 winter / UTC+3 summer).
    We convert to UTC so comparisons with MT5 candle Unix timestamps are correct.
    DST is handled automatically by ZoneInfo — no manual offset needed.
    """
    broker_tz = ZoneInfo(MT5_SERVER_TIMEZONE)
    for fmt in (
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%Y-%m-%d %H:%M",
        "%Y.%m.%d %H:%M:%S",   # MT5 native format: "2024.01.15 14:30:00"
        "%Y.%m.%d %H:%M",
    ):
        try:
            dt = datetime.strptime(ts.strip(), fmt)
            # Interpret parsed time as broker server time, then convert to UTC
            return dt.replace(tzinfo=broker_tz).astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _to_naive_utc(dt: datetime) -> datetime:
    """Strip tzinfo from a UTC-aware datetime for MT5 C-extension compatibility."""
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _price_in_candle(price: float, candle) -> bool:
    return (candle["low"] - _PRICE_TOLERANCE) <= price <= (candle["high"] + _PRICE_TOLERANCE)


def cross_check_screenshot(
    claim: ScreenshotData,
    symbol: str = MT5_SYMBOL,
) -> tuple[str, str | None]:
    """
    Cross-check a screenshot claim against MT5 M1 price data.

    Returns (verdict, notes) where verdict is one of:
      "confirmed" | "contradicted" | "unverifiable"
    """
    if claim.open_price is None:
        return "unverifiable", "Open price not extracted from screenshot"
    if claim.open_time is None:
        return "unverifiable", "Open time not extracted from screenshot"

    open_dt = _parse_dt(claim.open_time)
    if open_dt is None:
        return "unverifiable", f"Could not parse open time: {claim.open_time!r}"

    close_dt: datetime | None = None
    if claim.close_time:
        close_dt = _parse_dt(claim.close_time)

    try:
        import MetaTrader5 as mt5  # type: ignore

        if not mt5.initialize():
            return "unverifiable", f"MT5 not available: {mt5.last_error()}"

        # Fetch candles from (open_dt - buffer) to (close_dt + buffer) or +buffer if no close.
        # open_dt / close_dt are UTC-aware; strip tzinfo for MT5 C-extension compatibility.
        end_fetch = _to_naive_utc((close_dt or open_dt) + timedelta(minutes=_TIME_WINDOW_MIN))
        start_fetch = _to_naive_utc(open_dt - timedelta(minutes=_TIME_WINDOW_MIN))

        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, start_fetch, end_fetch)
        if rates is None or len(rates) == 0:
            return "unverifiable", "No MT5 candle data available for the claimed period"

        # ── Check claimed open price in the open_time window ──────────────────
        open_window_start = open_dt.timestamp() - _TIME_WINDOW_MIN * 60
        open_window_end = open_dt.timestamp() + _TIME_WINDOW_MIN * 60

        open_touched = any(
            open_window_start <= float(r["time"]) <= open_window_end
            and _price_in_candle(claim.open_price, r)
            for r in rates
        )

        if not open_touched:
            return (
                "contradicted",
                f"Claimed open {claim.open_price} at {claim.open_time} was never traded "
                f"in the ±{_TIME_WINDOW_MIN}-minute window (MT5 data checked).",
            )

        # ── If we also have close data, check it ──────────────────────────────
        if close_dt is not None and claim.close_price is not None:
            close_window_start = close_dt.timestamp() - _TIME_WINDOW_MIN * 60
            close_window_end = close_dt.timestamp() + _TIME_WINDOW_MIN * 60

            close_touched = any(
                close_window_start <= float(r["time"]) <= close_window_end
                and _price_in_candle(claim.close_price, r)
                for r in rates
            )

            if not close_touched:
                return (
                    "unverifiable",
                    f"Open price confirmed; close price {claim.close_price} at "
                    f"{claim.close_time} could not be verified in MT5 data.",
                )
            return "confirmed", None

        # Open was verified but no close data to check
        return "confirmed", "Open price confirmed; close price not checked (no close time extracted)"

    except ImportError:
        return "unverifiable", "MetaTrader5 package not installed"
    except Exception as exc:
        logger.warning("Screenshot cross-check failed: %s", exc)
        return "unverifiable", f"MT5 check error: {exc}"
