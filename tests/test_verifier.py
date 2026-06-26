"""
Verifier test suite — Phase 3.

Unit tests use mocked MT5 with synthetic candle arrays so they run without
MT5 open. The candle-walking algorithm is what matters; the MT5 connection
itself is tested via the offline test.

Integration tests (KNOWN_WIN / KNOWN_LOSS) remain skipped until you fill in
real trade data from your own history.
"""

from __future__ import annotations
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from backend.config import POINT_SIZE, DEFAULT_TP_PIPS
from backend.verifier import (
    verify_signal,
    MT5NotConnectedError,
    EntryNeverFilledError,
)

# ─── Synthetic candle helpers ─────────────────────────────────────────────────

CANDLE_DTYPE = np.dtype([
    ("time", np.int64),
    ("open", np.float64),
    ("high", np.float64),
    ("low", np.float64),
    ("close", np.float64),
    ("tick_volume", np.int64),
    ("spread", np.int32),
    ("real_volume", np.int64),
])

_T0 = datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)


def _candle(low: float, high: float, t: int = 0) -> np.ndarray:
    mid = (low + high) / 2
    return np.array([(t, mid, high, low, mid, 100, 1, 0)], dtype=CANDLE_DTYPE)


def _candles(*specs: tuple[float, float]) -> np.ndarray:
    """Build a candle array from (low, high) pairs."""
    return np.concatenate([_candle(lo, hi, i) for i, (lo, hi) in enumerate(specs)])


# ─── Integration test stubs (need real trade history) ─────────────────────────

KNOWN_WIN = dict(
    direction="BUY",
    entry=0.0,       # TODO: fill in from your trade history
    stop_loss=0.0,
    take_profit=0.0,
    posted_at=None,
)

KNOWN_LOSS = dict(
    direction="SELL",
    entry=0.0,
    stop_loss=0.0,
    take_profit=0.0,
    posted_at=None,
)


@pytest.mark.skip(reason="Fill in KNOWN_WIN values before enabling")
def test_clean_win_integration():
    result = verify_signal(**KNOWN_WIN)
    assert result.outcome == "win"
    assert result.points is not None and result.points > 0


@pytest.mark.skip(reason="Fill in KNOWN_LOSS values before enabling")
def test_clean_loss_integration():
    result = verify_signal(**KNOWN_LOSS)
    assert result.outcome == "loss"
    assert result.points is not None and result.points < 0


# ─── Unit tests (mocked MT5) ─────────────────────────────────────────────────
#
# BUY 2650 / SL 2640 / TP 2680 used throughout unless noted.
# Entry fills when candle low <= 2650 (BUY limit logic).

_BUY = dict(direction="BUY", entry=2650.0, stop_loss=2640.0, take_profit=2680.0,
            posted_at=_T0, symbol="XAUUSD")
_SELL = dict(direction="SELL", entry=2650.0, stop_loss=2660.0, take_profit=2620.0,
             posted_at=_T0, symbol="XAUUSD")


def _run(signal_kwargs: dict, candles: np.ndarray):
    with patch("MetaTrader5.initialize", return_value=True), \
         patch("MetaTrader5.copy_rates_from", return_value=candles):
        return verify_signal(**signal_kwargs)


def test_clean_win_buy():
    candles = _candles(
        (2652, 2655),   # before entry — price above 2650, no fill yet
        (2648, 2655),   # entry fills (low=2648 <= 2650), price doesn't hit TP/SL
        (2645, 2665),   # still in range
        (2648, 2670),   # getting close
        (2649, 2681),   # TP hit (high=2681 >= 2680)
    )
    result = _run(_BUY, candles)
    assert result.outcome == "win"
    assert result.points == pytest.approx((2680.0 - 2650.0) / POINT_SIZE)
    assert result.is_ambiguous is False


def test_clean_loss_buy():
    candles = _candles(
        (2648, 2655),   # entry fills
        (2645, 2660),   # normal candle
        (2638, 2648),   # SL hit (low=2638 <= 2640)
    )
    result = _run(_BUY, candles)
    assert result.outcome == "loss"
    assert result.points == pytest.approx((2640.0 - 2650.0) / POINT_SIZE)
    assert result.is_ambiguous is False


def test_ambiguous_candle():
    # Single candle after fill spans both SL (low <= 2640) and TP (high >= 2680)
    candles = _candles(
        (2648, 2655),   # entry fills
        (2635, 2685),   # ambiguous: low=2635 AND high=2685
    )
    result = _run(_BUY, candles)
    assert result.outcome == "ambiguous_loss"
    assert result.is_ambiguous is True
    assert result.points == pytest.approx((2640.0 - 2650.0) / POINT_SIZE)


def test_entry_never_filled():
    # All candles have low > 2650 — price never dips to entry
    candles = _candles(*[(2655, 2665)] * 20)
    with patch("MetaTrader5.initialize", return_value=True), \
         patch("MetaTrader5.copy_rates_from", return_value=candles):
        with pytest.raises(EntryNeverFilledError):
            verify_signal(**_BUY)


def test_mt5_offline_raises():
    with patch("MetaTrader5.initialize", return_value=False), \
         patch("MetaTrader5.last_error", return_value=(-1, "not connected")):
        with pytest.raises(MT5NotConnectedError):
            verify_signal(**_BUY)


def test_window_expired_unresolved():
    # Price meanders between 2645–2665 for all candles — never hits SL (2640) or TP (2680)
    n = 2880  # full 48 h of 1-min candles
    candles = _candles(*[(2645, 2665)] * n)
    result = _run(_BUY, candles)
    assert result.outcome == "unresolved"
    assert result.points is None
    assert result.candles_walked == n


def test_no_tp_uses_default():
    # BUY with no TP stated — verifier should apply DEFAULT_TP_PIPS (50 pts)
    default_tp = 2650.0 + DEFAULT_TP_PIPS   # 2700
    candles = _candles(
        (2648, 2655),            # entry fills
        (2650, default_tp + 1),  # price hits default TP (2701 > 2700)
    )
    signal = dict(direction="BUY", entry=2650.0, stop_loss=2640.0,
                  take_profit=None, posted_at=_T0, symbol="XAUUSD")
    with patch("MetaTrader5.initialize", return_value=True), \
         patch("MetaTrader5.copy_rates_from", return_value=candles):
        result = verify_signal(**signal)
    assert result.outcome == "win"
    assert result.points == pytest.approx(DEFAULT_TP_PIPS)


def test_clean_win_sell():
    # SELL 2650, SL 2660, TP 2620: price rises to entry, then falls to TP
    candles = _candles(
        (2648, 2648),   # before fill — high=2648 < 2650, no fill
        (2648, 2652),   # SELL entry fills (high=2652 >= 2650)
        (2645, 2655),   # normal
        (2618, 2645),   # TP hit (low=2618 <= 2620)
    )
    result = _run(_SELL, candles)
    assert result.outcome == "win"
    assert result.points == pytest.approx((2650.0 - 2620.0) / POINT_SIZE)
