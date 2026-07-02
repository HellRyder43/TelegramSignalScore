"""
Text signal parser — Phase 3 implementation.

Extracts structured signal data from raw Telegram message text via
regex / rule-based matching.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Literal


SignalType = Literal["text", "zone_estimated"]
Direction = Literal["BUY", "SELL"]

# ─── Compiled patterns ────────────────────────────────────────────────────────

_DIRECTION_RE = re.compile(r'\b(BUY|SELL|LONG|SHORT)\b', re.IGNORECASE)

# Includes "CL" / "cut loss" / "cutloss" — how many gold channels write their
# stop-loss (e.g. "Price @ 4016-4008 Cl 4006 Tp open").
_SL_RE = re.compile(
    r'\b(?:sl|stop[\s\-]?loss|stop|cl|cut[\s\-]?loss)\b[\s:]*([0-9]{3,6}(?:\.[0-9]+)?)',
    re.IGNORECASE,
)

# Matches tp, tp1, tp2, tp3, t1, t2, t3, target, target1…3, take profit
_TP_ALL_RE = re.compile(
    r'\b(?:tp[1-3]?|t[1-3]|take[\s\-]?profit[1-3]?|target[1-3]?)\b[\s:]*([0-9]{3,6}(?:\.[0-9]+)?)',
    re.IGNORECASE,
)

# Explicit entry label
_ENTRY_LABEL_RE = re.compile(
    r'\b(?:entry|enter|price)\b[\s:]*([0-9]{3,6}(?:\.[0-9]+)?)\s*[-–]?\s*([0-9]{3,6}(?:\.[0-9]+)?)?',
    re.IGNORECASE,
)

# "@2650" or "@ 2650" or "@ 2650 - 2655" (range)
_AT_RE = re.compile(
    r'@[\s]*([0-9]{3,6}(?:\.[0-9]+)?)'
    r'(?:\s*[-–]\s*([0-9]{3,6}(?:\.[0-9]+)?))?'
)

# Price after BUY/SELL/LONG/SHORT, optionally skipping one instrument token
# (e.g. "BUY GOLD 2650" or "BUY XAUUSD 2650" or "BUY 2650")
_PRICE_AFTER_DIR_RE = re.compile(
    r'\b(?:BUY|SELL|LONG|SHORT)\b'
    r'(?:\s+[A-Za-z][A-Za-z0-9/._]*)?'   # skip optional instrument name
    r'[\s@:]*'
    r'([0-9]{3,6}(?:\.[0-9]+)?)'
    r'(?:\s*[-–]\s*([0-9]{3,6}(?:\.[0-9]+)?))?',
    re.IGNORECASE,
)

# Standalone price range like "2650-2655" or "2650 – 2655"
_RANGE_RE = re.compile(
    r'([0-9]{3,6}(?:\.[0-9]+)?)\s*[-–]\s*([0-9]{3,6}(?:\.[0-9]+)?)'
)

_DIRECTION_MAP = {"LONG": "BUY", "SHORT": "SELL", "BUY": "BUY", "SELL": "SELL"}


@dataclass
class ParsedSignal:
    signal_type: SignalType
    direction: Direction | None
    entry: float | None
    entry_low: float | None          # zone_estimated only
    entry_high: float | None         # zone_estimated only
    stop_loss: float | None
    take_profit_1: float | None
    take_profit_2: float | None
    take_profit_3: float | None
    raw_text: str
    confidence: float                # 0.0 – 1.0


def parse_text_signal(text: str) -> ParsedSignal | None:
    """
    Parse a raw Telegram message into a ParsedSignal.

    Returns None if the message is not a recognizable signal (missing direction
    or entry price).
    """
    # ── Direction ──────────────────────────────────────────────────────────────
    dir_match = _DIRECTION_RE.search(text)
    if not dir_match:
        return None
    direction: Direction = _DIRECTION_MAP[dir_match.group(1).upper()]  # type: ignore[assignment]

    # ── Stop loss ──────────────────────────────────────────────────────────────
    sl_match = _SL_RE.search(text)
    stop_loss = float(sl_match.group(1)) if sl_match else None

    # ── Take profits (up to 3) ─────────────────────────────────────────────────
    tp_matches = list(_TP_ALL_RE.finditer(text))
    tp_values = [float(m.group(1)) for m in tp_matches]
    take_profit_1 = tp_values[0] if len(tp_values) > 0 else None
    take_profit_2 = tp_values[1] if len(tp_values) > 1 else None
    take_profit_3 = tp_values[2] if len(tp_values) > 2 else None

    # ── Entry ──────────────────────────────────────────────────────────────────
    entry: float | None = None
    entry_low: float | None = None
    entry_high: float | None = None
    signal_type: SignalType = "text"

    # 1. Explicit "entry: 2650" or "entry: 2650-2655"
    el_match = _ENTRY_LABEL_RE.search(text)
    if el_match:
        v1 = float(el_match.group(1))
        v2 = float(el_match.group(2)) if el_match.group(2) else None
        if v2 and abs(v2 - v1) < 50:   # treat as range
            entry_low, entry_high = min(v1, v2), max(v1, v2)
            entry = (entry_low + entry_high) / 2
            signal_type = "zone_estimated"
        else:
            entry = v1

    # 2. "@ 2650" or "@ 2650 - 2655"
    if entry is None:
        at_match = _AT_RE.search(text)
        if at_match:
            v1 = float(at_match.group(1))
            v2 = float(at_match.group(2)) if at_match.group(2) else None
            if v2 and abs(v2 - v1) < 50:
                entry_low, entry_high = min(v1, v2), max(v1, v2)
                entry = (entry_low + entry_high) / 2
                signal_type = "zone_estimated"
            else:
                entry = v1

    # 3. Price immediately after direction keyword (possibly a range)
    if entry is None:
        pad_match = _PRICE_AFTER_DIR_RE.search(text)
        if pad_match:
            v1 = float(pad_match.group(1))
            v2 = float(pad_match.group(2)) if pad_match.group(2) else None
            if v2 and abs(v2 - v1) < 50:
                entry_low, entry_high = min(v1, v2), max(v1, v2)
                entry = (entry_low + entry_high) / 2
                signal_type = "zone_estimated"
            else:
                entry = v1

    if entry is None:
        return None

    # ── Sanity check ───────────────────────────────────────────────────────────
    # For BUY: SL < entry < TP1 (if both present).
    # For SELL: TP1 < entry < SL (if both present).
    # Reject only if the relationship is clearly inverted — don't reject partial signals.
    if stop_loss and take_profit_1:
        if direction == "BUY" and not (stop_loss < entry < take_profit_1):
            return None
        if direction == "SELL" and not (take_profit_1 < entry < stop_loss):
            return None

    # ── Confidence ─────────────────────────────────────────────────────────────
    if stop_loss and take_profit_1:
        confidence = 1.0
    elif stop_loss:
        confidence = 0.7   # SL stated, TP missing (common for zone signals)
    elif take_profit_1:
        confidence = 0.6   # TP stated, SL missing
    else:
        confidence = 0.4   # only direction + entry

    return ParsedSignal(
        signal_type=signal_type,
        direction=direction,
        entry=entry,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        take_profit_3=take_profit_3,
        raw_text=text,
        confidence=confidence,
    )


_parser_logger = __import__("logging").getLogger(__name__)


def parse_signal_with_ai_fallback(text: str) -> "tuple[ParsedSignal | None, str]":
    """
    Try regex parse first; if it returns None and AI is enabled, try Claude.

    Returns (ParsedSignal | None, parse_method) where parse_method is
    "regex" or "ai_fallback". Never raises.
    """
    from backend.config import ANTHROPIC_API_KEY, AI_PARSER_ENABLED

    parsed = parse_text_signal(text)
    if parsed is not None:
        return parsed, "regex"

    if not (AI_PARSER_ENABLED and ANTHROPIC_API_KEY):
        return None, "regex"

    try:
        from backend.ai.signal_parser import ai_parse_signal
        ai_parsed = ai_parse_signal(text)
        return ai_parsed, ("ai_fallback" if ai_parsed is not None else "regex")
    except Exception as exc:
        _parser_logger.warning("AI signal parser failed (non-fatal): %s", exc)
        return None, "regex"


def classify_message(text: str | None, has_image: bool) -> str:
    """
    Classify a message into one of:
      text_signal | zone_image | mt5_screenshot | non_signal | image_deferred

    Rules:
    - Text only: try parsing → text_signal or non_signal.
    - Image + parseable caption: text_signal (we can still verify the text).
    - Image + no parseable text + no Anthropic key: image_deferred.
    - Image + no parseable text + Anthropic key present: zone_image (Phase 7 refines further).
    """
    from backend.config import ANTHROPIC_API_KEY

    text_parseable = bool(text and parse_text_signal(text) is not None)

    if not has_image:
        return "text_signal" if text_parseable else "non_signal"

    # Has image — but if the caption is already a parseable signal, classify as text_signal.
    if text_parseable:
        return "text_signal"

    # Image with no parseable text.
    if not ANTHROPIC_API_KEY:
        return "image_deferred"

    # Phase 7 will distinguish zone_image vs mt5_screenshot via vision API.
    return "zone_image"
