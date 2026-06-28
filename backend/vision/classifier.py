"""
Image classifier — Phase 7.

Sends a Telegram message image to Claude's vision API and returns a
classification label used to route the message to the right parser.
"""

from __future__ import annotations

import base64
import logging

import anthropic

from backend.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL

logger = logging.getLogger(__name__)

_VALID_LABELS = frozenset({"chart_zone", "mt5_screenshot", "other"})

_CLASSIFY_PROMPT = """\
Classify this image into exactly one of these categories:

chart_zone      — A trading chart (candlestick or line) that shows XAUUSD/Gold price action
                  with an entry zone, buy/sell area, or trading setup marked on it.
                  May include support/resistance lines, colored zones, or annotations.

mt5_screenshot  — A MetaTrader 5 trade history or account statement screenshot showing a
                  closed trade result: typically displays entry price, exit price, profit/loss,
                  and trade times. Often shows green "profit" text.

other           — Anything else: educational content, hype text, logos, unrelated images,
                  or charts without a clear trading setup marked.

Reply with ONLY the label (one of: chart_zone, mt5_screenshot, other). No other text."""


def classify_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Classify a Telegram message image.

    Returns "chart_zone" | "mt5_screenshot" | "other".
    Falls back to "other" on API errors or unexpected responses.
    """
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY is not set in .env")

    b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    try:
        response = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=20,
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
                    {"type": "text", "text": _CLASSIFY_PROMPT},
                ],
            }],
        )
        label = response.content[0].text.strip().lower()
        if label not in _VALID_LABELS:
            logger.warning("Unexpected classification label: %r — defaulting to 'other'", label)
            return "other"
        return label
    except Exception as exc:
        logger.error("Vision classification failed: %s", exc)
        raise
