"""
Chart zone parser — Phase 7.

Sends a chart-zone image (and optional caption text) to Claude and extracts
a structured trading signal with entry zone bounds, SL, and TP levels.

Returns a ParsedSignal with signal_type="zone_estimated". Zone-estimated signals
are tracked separately from stated-level text signals and weighted lower in scoring.
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

_CHART_PROMPT = """\
This is a XAUUSD (Gold) trading chart. Extract the trading setup marked on it.

{caption_section}

Return a JSON object with these exact fields (use null for any level you cannot clearly read):
{{
  "direction":    "BUY" or "SELL",
  "entry_low":    <lower price of the entry zone, a number>,
  "entry_high":   <upper price of the entry zone, a number>,
  "stop_loss":    <stop loss price, a number or null>,
  "take_profit_1": <first take profit price, a number or null>,
  "take_profit_2": <second take profit price, a number or null>,
  "take_profit_3": <third take profit price, a number or null>
}}

XAUUSD prices are in the 1800–3500 range. Return ONLY the JSON object, nothing else."""

_CAPTION_PREFIX = "The message caption text is:\n"


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
        return f if 500 <= f <= 5000 else None   # sanity range for XAUUSD
    except (TypeError, ValueError):
        return None


def parse_chart_zone(
    image_bytes: bytes,
    caption: str | None = None,
    mime_type: str = "image/jpeg",
) -> ParsedSignal | None:
    """
    Extract a trading setup from a chart screenshot.

    Returns ParsedSignal (signal_type="zone_estimated") or None if the image
    does not contain a readable setup.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")

    caption_section = f"{_CAPTION_PREFIX}{caption}" if caption else ""
    prompt = _CHART_PROMPT.format(caption_section=caption_section)

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64,
                        },
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except Exception as exc:
        logger.error("Chart zone API call failed: %s", exc)
        raise

    raw = response.content[0].text
    data = _extract_json(raw)
    if data is None:
        logger.warning("Could not extract JSON from chart parser response: %r", raw[:200])
        return None

    direction_raw = str(data.get("direction", "")).upper()
    if direction_raw not in ("BUY", "SELL"):
        logger.warning("Chart parser returned invalid direction: %r", direction_raw)
        return None

    entry_low = _to_float(data.get("entry_low"))
    entry_high = _to_float(data.get("entry_high"))

    if entry_low is None or entry_high is None:
        logger.info("Chart parser: no entry zone extracted")
        return None

    # Ensure consistent ordering and reject implausibly wide zones (>200 pts)
    if entry_low > entry_high:
        entry_low, entry_high = entry_high, entry_low
    if entry_high - entry_low > 200:
        logger.info("Chart parser: zone too wide (%.1f pts), rejecting", entry_high - entry_low)
        return None

    entry = (entry_low + entry_high) / 2
    stop_loss = _to_float(data.get("stop_loss"))
    take_profit_1 = _to_float(data.get("take_profit_1"))
    take_profit_2 = _to_float(data.get("take_profit_2"))
    take_profit_3 = _to_float(data.get("take_profit_3"))

    # Basic directional sanity: SL should be on the wrong side of entry for the direction
    if stop_loss and take_profit_1:
        if direction_raw == "BUY" and not (stop_loss < entry < take_profit_1):
            logger.info("Chart parser: BUY signal has inverted levels, rejecting")
            return None
        if direction_raw == "SELL" and not (take_profit_1 < entry < stop_loss):
            logger.info("Chart parser: SELL signal has inverted levels, rejecting")
            return None

    # Confidence is lower for zone signals (estimated from visual, not stated)
    if stop_loss and take_profit_1:
        confidence = 0.7
    elif stop_loss or take_profit_1:
        confidence = 0.5
    else:
        confidence = 0.4

    return ParsedSignal(
        signal_type="zone_estimated",
        direction=direction_raw,    # type: ignore[arg-type]
        entry=entry,
        entry_low=entry_low,
        entry_high=entry_high,
        stop_loss=stop_loss,
        take_profit_1=take_profit_1,
        take_profit_2=take_profit_2,
        take_profit_3=take_profit_3,
        raw_text=f"[Chart zone] {caption or ''}".strip(),
        confidence=confidence,
    )
