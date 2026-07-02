"""
Reprocess image_deferred messages using the Claude vision API.

Run this after adding ANTHROPIC_API_KEY to .env to retroactively classify and
parse all images that were skipped during backfill or live ingestion.

Usage:
    python scripts/reprocess_images.py
    python scripts/reprocess_images.py --limit 100
    python scripts/reprocess_images.py --channel @some_channel --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

load_dotenv()

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    TG_API_ID,
    TG_API_HASH,
    TG_BACKFILL_SESSION_NAME,
    MT5_SYMBOL,
    ANTHROPIC_API_KEY,
)
from backend.db_utils import maybe_one

# Reuse the backfill session (separate from the live ingestor's session) so this
# script can run alongside the listener without Telethon's "two clients sharing
# one session" hang. Resolve to an absolute path from the project root.
_PROJECT_ROOT = Path(__file__).parent.parent
_SESSION_PATH = str(_PROJECT_ROOT / TG_BACKFILL_SESSION_NAME)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("reprocess")


def _has_image(msg) -> bool:
    media = getattr(msg, "media", None)
    if media is None:
        return False
    if isinstance(media, MessageMediaPhoto):
        return True
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc and getattr(doc, "mime_type", "").startswith("image/"):
            return True
    return False


def _get_image_mime(msg) -> str:
    media = getattr(msg, "media", None)
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "")
            if mime.startswith("image/"):
                return mime
    return "image/jpeg"


async def _reprocess_message(
    db,
    tg_client: TelegramClient,
    row: dict,
    channel_telegram_id: int,
    channel_row: dict,
) -> str:
    """
    Re-fetch a Telegram message, classify it with vision, and update the DB.
    Returns the final message_type string.
    """
    from backend.vision.classifier import classify_image
    from backend.vision.chart_parser import parse_chart_zone
    from backend.vision.screenshot_parser import parse_mt5_screenshot
    from backend.vision.screenshot_checker import cross_check_screenshot
    from backend.parser import parse_text_signal

    tg_msg_id: int = row["telegram_message_id"]
    caption: str | None = row.get("content")

    # Re-fetch the message from Telegram to get the media reference
    try:
        msgs = await tg_client.get_messages(channel_telegram_id, ids=[tg_msg_id])
        tg_msg = msgs[0] if msgs else None
    except Exception as exc:
        logger.warning("Could not fetch msg=%s from Telegram: %s", tg_msg_id, exc)
        return "image_deferred"

    if tg_msg is None or not _has_image(tg_msg):
        logger.info("msg=%s no longer has media (possibly deleted)", tg_msg_id)
        return "image_deferred"

    img_mime = _get_image_mime(tg_msg)
    img_bytes: bytes | None = await tg_msg.download_media(bytes)
    if not img_bytes:
        logger.warning("Could not download media for msg=%s", tg_msg_id)
        return "image_deferred"

    # Classify
    try:
        image_class = classify_image(img_bytes, img_mime)
    except Exception as exc:
        logger.warning("Vision classify failed for msg=%s: %s", tg_msg_id, exc)
        return "image_deferred"

    if image_class == "chart_zone":
        final_type = "zone_image"
    elif image_class == "mt5_screenshot":
        final_type = "mt5_screenshot"
    else:
        final_type = "non_signal"

    # Update message type in DB
    db.table("messages").update({"message_type": final_type}).eq("id", row["id"]).execute()

    posted_at = row.get("posted_at", "")
    try:
        posted_dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except Exception:
        posted_dt = datetime.now(timezone.utc)

    # Type-specific processing
    if final_type == "zone_image":
        try:
            parsed = parse_chart_zone(img_bytes, caption, img_mime)
        except Exception as exc:
            logger.warning("Chart parse failed for msg=%s: %s", tg_msg_id, exc)
            parsed = None

        if parsed:
            db.table("signals").insert({
                "channel_id": channel_row["id"],
                "message_id": row["id"],
                "signal_type": parsed.signal_type,
                "source": row.get("source", "backfill"),
                "direction": parsed.direction,
                "entry": parsed.entry,
                "entry_low": parsed.entry_low,
                "entry_high": parsed.entry_high,
                "stop_loss": parsed.stop_loss,
                "take_profit_1": parsed.take_profit_1,
                "take_profit_2": parsed.take_profit_2,
                "take_profit_3": parsed.take_profit_3,
                "raw_text": parsed.raw_text,
                "posted_at": posted_dt.isoformat(),
                "confidence": parsed.confidence,
                "parse_method": "vision",
            }).execute()
            db.table("channels").update(
                {"last_signal_at": posted_dt.isoformat()}
            ).eq("id", channel_row["id"]).execute()
            logger.info("msg=%s → zone_image signal inserted (dir=%s)", tg_msg_id, parsed.direction)
        else:
            logger.info("msg=%s → zone_image but no levels extracted", tg_msg_id)

    elif final_type == "mt5_screenshot":
        try:
            claim = parse_mt5_screenshot(img_bytes, img_mime)
        except Exception as exc:
            logger.warning("Screenshot parse failed for msg=%s: %s", tg_msg_id, exc)
            claim = None

        if claim:
            verdict, notes = cross_check_screenshot(claim, MT5_SYMBOL)
            db.table("screenshot_claims").insert({
                "channel_id": channel_row["id"],
                "message_id": row["id"],
                "claimed_direction": claim.direction,
                "claimed_open": claim.open_price,
                "claimed_close": claim.close_price,
                "claimed_profit_pts": claim.profit_pts,
                "claimed_open_time": claim.open_time,
                "claimed_close_time": claim.close_time,
                "verdict": verdict,
                "posted_at": posted_dt.isoformat(),
                "notes": notes,
            }).execute()

            # Update channel screenshot counts
            ch = maybe_one(
                db.table("channels")
                .select("screenshot_confirmed, screenshot_contradicted")
                .eq("id", channel_row["id"])
            )
            if ch:
                if verdict == "confirmed":
                    db.table("channels").update(
                        {"screenshot_confirmed": ch["screenshot_confirmed"] + 1}
                    ).eq("id", channel_row["id"]).execute()
                elif verdict == "contradicted":
                    db.table("channels").update(
                        {"screenshot_contradicted": ch["screenshot_contradicted"] + 1}
                    ).eq("id", channel_row["id"]).execute()

            logger.info("msg=%s → mt5_screenshot verdict=%s", tg_msg_id, verdict)
        else:
            logger.info("msg=%s → mt5_screenshot but no trade data extracted", tg_msg_id)

    return final_type


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reprocess image_deferred Telegram messages using Claude vision API"
    )
    parser.add_argument("--channel", help="Filter by @username or channel name (optional)")
    parser.add_argument("--limit", type=int, default=500, help="Max messages to reprocess (default 500)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between API calls (default 1.0)")
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY is not set in .env — cannot run vision API calls")
        sys.exit(1)
    if not TG_API_ID or not TG_API_HASH:
        logger.error("TG_API_ID and TG_API_HASH must be set in .env")
        sys.exit(1)

    db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # Fetch image_deferred messages with their channel data
    q = (
        db.table("messages")
        .select("*, channels(id, telegram_id, name)")
        .eq("message_type", "image_deferred")
        .limit(args.limit)
    )
    if args.channel:
        # Filter by channel name/username
        channel_rows = (
            db.table("channels")
            .select("id")
            .ilike("name", f"%{args.channel.lstrip('@')}%")
            .execute()
            .data
        )
        if not channel_rows:
            logger.error("No channel found matching %r", args.channel)
            sys.exit(1)
        channel_ids = [r["id"] for r in channel_rows]
        q = q.in_("channel_id", channel_ids)

    rows = q.execute().data
    logger.info("Found %d image_deferred messages to reprocess", len(rows))

    if not rows:
        return

    tg_client = TelegramClient(_SESSION_PATH, TG_API_ID, TG_API_HASH)

    logger.info("Connecting to Telegram (reprocess session)...")
    try:
        await asyncio.wait_for(tg_client.connect(), timeout=30)
    except asyncio.TimeoutError:
        logger.error("Could not connect within 30s — likely a network issue. Try again.")
        sys.exit(1)
    except Exception as exc:
        logger.error("Telegram connection failed: %s", exc)
        sys.exit(1)

    if not await tg_client.is_user_authorized():
        logger.info(
            "First-time login for this session — Telegram will ask for your phone "
            "number and a login code (one time only)."
        )
        await tg_client.start()  # interactive; connection already established above
    logger.info("Connected.")

    # Telethon must have "seen" a channel before we can fetch its messages by the
    # bare numeric telegram_id stored in the DB. Backfill records channels by their
    # unmarked entity.id (a plain positive int); handed straight to get_messages,
    # Telethon can't tell it's a channel and treats it as a PeerUser, failing with
    # "Could not find the input entity for PeerUser(...)". Loading dialogs once
    # fills the session entity cache with every joined channel, after which
    # get_messages(<id>, ...) resolves. (See Telethon docs: concepts/entities.)
    logger.info("Loading dialogs to populate the entity cache...")
    try:
        await tg_client.get_dialogs()
    except Exception as exc:
        logger.warning(
            "Could not load dialogs — entity resolution may still fail: %s", exc
        )

    counts: dict[str, int] = {"zone_image": 0, "mt5_screenshot": 0, "non_signal": 0, "image_deferred": 0}

    for i, row in enumerate(rows, 1):
        channel_data = row.get("channels") or {}
        channel_telegram_id: int = channel_data.get("telegram_id")
        if not channel_telegram_id:
            logger.warning("msg=%s has no channel telegram_id, skipping", row.get("id"))
            continue

        channel_row = {"id": row["channel_id"], **channel_data}

        final_type = await _reprocess_message(db, tg_client, row, channel_telegram_id, channel_row)
        counts[final_type] = counts.get(final_type, 0) + 1

        if i % 10 == 0:
            logger.info("Progress: %d/%d processed", i, len(rows))

        # Respect Anthropic rate limits
        if args.delay > 0:
            await asyncio.sleep(args.delay)

    await tg_client.disconnect()

    logger.info(
        "Done. Results: %d zone_image, %d mt5_screenshot, %d non_signal, %d still deferred",
        counts.get("zone_image", 0),
        counts.get("mt5_screenshot", 0),
        counts.get("non_signal", 0),
        counts.get("image_deferred", 0),
    )


if __name__ == "__main__":
    asyncio.run(main())
