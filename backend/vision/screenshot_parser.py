"""
MT5 screenshot parser — Phase 7.

Sends an MT5 profit screenshot to Claude and extracts the claimed trade details.
The result feeds the screenshot cross-checker for fabrication detection.

IMPORTANT: screenshots always show wins. They are CLAIMS about past trades, not
forward signals. They feed the integrity score only, never the win rate.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass

import anthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)


@dataclass
class ScreenshotData:
    direction: str | None          # "BUY" | "SELL" | None
    open_price: float | None       # entry price
    close_price: float | None      # exit price
    open_time: str | None          # ISO datetime string or None
    close_time: str | None         # ISO datetime string or None
    profit_pts: float | None       # claimed profit in points (always positive)


_SCREENSHOT_PROMPT = """\
This is a MetaTrader 5 (MT5) trade result screenshot for XAUUSD (Gold).
Extract the closed trade details.

Return a JSON object with these exact fields (use null for any value you cannot read):
{
  "direction":   "BUY" or "SELL" or null,
  "open_price":  <entry price as a number, e.g. 2645.50>,
  "close_price": <exit/close price as a number, e.g. 2680.00>,
  "open_time":   "<date and time the trade was opened, ISO format YYYY-MM-DDTHH:MM:SS or null>",
  "close_time":  "<date and time the trade was closed, ISO format YYYY-MM-DDTHH:MM:SS or null>",
  "profit_pts":  <profit in points as a positive number, e.g. 34.5>
}

XAUUSD prices are in the 1800–3500 range.
Return ONLY the JSON object, nothing else."""


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
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _to_str(v: object) -> str | None:
    if v is None or str(v).strip().lower() == "null":
        return None
    return str(v).strip() or None


def parse_mt5_screenshot(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> ScreenshotData | None:
    """
    Extract trade details from an MT5 profit screenshot.

    Returns ScreenshotData or None if extraction fails or yields no usable data.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")

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
                    {"type": "text", "text": _SCREENSHOT_PROMPT},
                ],
            }],
        )
    except Exception as exc:
        logger.error("Screenshot parser API call failed: %s", exc)
        raise

    raw = response.content[0].text
    data = _extract_json(raw)
    if data is None:
        logger.warning("Could not extract JSON from screenshot parser response: %r", raw[:200])
        return None

    direction_raw = str(data.get("direction") or "").upper()
    direction = direction_raw if direction_raw in ("BUY", "SELL") else None

    open_price = _to_float(data.get("open_price"))
    close_price = _to_float(data.get("close_price"))

    # Need at least a price to be worth storing
    if open_price is None and close_price is None:
        logger.info("Screenshot parser: no prices extracted")
        return None

    return ScreenshotData(
        direction=direction,
        open_price=open_price,
        close_price=close_price,
        open_time=_to_str(data.get("open_time")),
        close_time=_to_str(data.get("close_time")),
        profit_pts=_to_float(data.get("profit_pts")),
    )
