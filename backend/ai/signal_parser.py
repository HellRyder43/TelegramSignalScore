"""
AI signal parser — Phase 8.

Fallback parser called only when the regex-based parse_text_signal() returns None.
Uses Claude to extract direction, entry, SL, and TP from non-standard signal text.

Never call this directly from outside this package; use
parser.parse_signal_with_ai_fallback() which applies the regex first.
"""

from __future__ import annotations

import base64
import json
import logging
import re

import anthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from backend.parser import ParsedSignal

logger = logging.getLogger(__name__)

_PARSE_PROMPT = """\
You are a XAUUSD (Gold) trading signal extractor.

Read the message below and extract the trading signal levels if this is a GENUINE
FORWARD signal (posted BEFORE the trade plays out). Return a JSON object:

{
  "direction":     "BUY" or "SELL" or null,
  "entry":         <price number or null>,
  "entry_low":     <lower bound of entry zone or null>,
  "entry_high":    <upper bound of entry zone or null>,
  "stop_loss":     <stop loss price or null>,
  "take_profit_1": <first target or null>,
  "take_profit_2": <second target or null>,
  "take_profit_3": <third target or null>
}

Rules:
- XAUUSD prices are in the range 500–5000. Reject any price outside this range (return null for that field).
- If direction cannot be determined, return {"direction": null} and nothing else.
- If this is commentary, analysis, or a retrospective post (e.g. "we hit our target"), return {"direction": null}.
- Return ONLY the JSON object, no other text.

Message:
"""


def _extract_json(text: str) -> dict | None:
    m = re.search(r"```(?:json)?\s*\n?(\{.*?\})\s*\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _to_float(v: object) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return f if 500 <= f <= 5000 else None
    except (TypeError, ValueError):
        return None


def ai_parse_signal(text: str) -> ParsedSignal | None:
    """
    Ask Claude to extract a ParsedSignal from non-standard signal text.

    Returns None if:
    - ANTHROPIC_API_KEY is not set
    - The text is not a recognisable forward signal
    - Any API or parsing error occurs

    Always returns confidence <= 0.5 (AI fallback is less reliable than regex).
    Never raises.
    """
    if not ANTHROPIC_API_KEY:
        return None

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": _PARSE_PROMPT + text[:3000],
            }],
        )
        raw = response.content[0].text
        data = _extract_json(raw)
        if data is None:
            logger.debug("AI parser: no JSON in response for text=%r", text[:80])
            return None

        direction_raw = str(data.get("direction") or "").upper()
        if direction_raw not in ("BUY", "SELL"):
            return None

        direction = direction_raw  # type: ignore[assignment]

        entry_low = _to_float(data.get("entry_low"))
        entry_high = _to_float(data.get("entry_high"))
        entry = _to_float(data.get("entry"))

        if entry is None and entry_low is not None and entry_high is not None:
            entry = (entry_low + entry_high) / 2

        if entry is None:
            return None

        stop_loss = _to_float(data.get("stop_loss"))
        tp1 = _to_float(data.get("take_profit_1"))
        tp2 = _to_float(data.get("take_profit_2"))
        tp3 = _to_float(data.get("take_profit_3"))

        # Directional sanity check (same as regex parser)
        if stop_loss and tp1:
            if direction == "BUY" and not (stop_loss < entry < tp1):
                return None
            if direction == "SELL" and not (tp1 < entry < stop_loss):
                return None

        signal_type = "zone_estimated" if (entry_low and entry_high) else "text"

        # Confidence is capped at 0.5 for AI-fallback parses
        if stop_loss and tp1:
            confidence = 0.5
        elif stop_loss or tp1:
            confidence = 0.4
        else:
            confidence = 0.3

        return ParsedSignal(
            signal_type=signal_type,  # type: ignore[arg-type]
            direction=direction,  # type: ignore[arg-type]
            entry=entry,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            take_profit_3=tp3,
            raw_text=text,
            confidence=confidence,
        )

    except Exception as exc:
        logger.warning("AI signal parser failed (non-fatal): %s", exc)
        return None
