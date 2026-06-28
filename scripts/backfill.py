"""
backfill.py — pull historical Telegram messages into Supabase.

All messages are stored with source='backfill'. Backfilled signals count at
reduced weight in the Trust Score (see BACKFILL_SIGNAL_WEIGHT in config.py).
Re-running is safe: messages already in the database are skipped.

Usage:
    python -m scripts.backfill --channel -1001234567890 [--limit 500]
    python -m scripts.backfill --channel @channelUsername [--limit 200]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import timezone
from pathlib import Path

# Suppress Telethon's "Server sent a very new message" warnings — these appear
# for channels that use scheduled or system messages with large internal IDs.
# They are harmless and not related to the signals we care about.
logging.getLogger("telethon.client.updates").setLevel(logging.ERROR)
logging.getLogger("telethon").setLevel(logging.ERROR)

from dotenv import load_dotenv

load_dotenv()

from supabase import create_client, Client
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, DocumentAttributeSticker

from backend.config import (
    TG_API_ID,
    TG_API_HASH,
    TG_BACKFILL_SESSION_NAME,
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
)
from backend.parser import classify_message, parse_text_signal

# Resolve session file relative to the project root (two levels up from this
# script), so it is always found regardless of which directory you run from.
#
# Backfill uses its OWN session (separate from the live ingestor). Telethon cannot
# share one session file across two running processes — doing so makes the second
# one hang forever at connect. A separate session lets backfill run concurrently
# with the live listener.
_PROJECT_ROOT = Path(__file__).parent.parent
_SESSION_PATH = str(_PROJECT_ROOT / TG_BACKFILL_SESSION_NAME)

logger = logging.getLogger(__name__)


def _is_sticker(doc) -> bool:
    # Static stickers are image/webp documents but are never charts/screenshots.
    # Excluding them keeps stickers out of the (deferred) vision pipeline.
    attrs = getattr(doc, "attributes", None) or []
    return any(isinstance(a, DocumentAttributeSticker) for a in attrs)


def _has_image(message) -> bool:
    media = getattr(message, "media", None)
    if media is None:
        return False
    if isinstance(media, MessageMediaPhoto):
        return True
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc and getattr(doc, "mime_type", "").startswith("image/") and not _is_sticker(doc):
            return True
    return False


def _upsert_channel(
    db: Client,
    tg_id: int,
    name: str,
    username: str | None,
    member_count: int | None,
) -> dict:
    existing = (
        db.table("channels")
        .select("*")
        .eq("telegram_id", tg_id)
        .maybe_single()
        .execute()
        .data
    )
    if existing:
        return existing
    result = db.table("channels").insert({
        "telegram_id": tg_id,
        "name": name,
        "username": username,
        "member_count": member_count,
    }).execute()
    if not result.data:
        raise RuntimeError(f"Failed to insert channel {tg_id}")
    return result.data[0]


async def backfill(channel_ref: str, limit: int) -> None:
    if not TG_API_ID or not TG_API_HASH:
        print("Error: TG_API_ID and TG_API_HASH must be set in .env")
        sys.exit(1)
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    client = TelegramClient(_SESSION_PATH, TG_API_ID, TG_API_HASH)

    print("Connecting to Telegram... ", end="", flush=True)
    # Time-box the network connect so a stall can never hang silently. The
    # interactive login below is deliberately NOT timed, so one-time code entry
    # isn't cut off.
    try:
        await asyncio.wait_for(client.connect(), timeout=30)
    except asyncio.TimeoutError:
        print("TIMED OUT")
        print(
            "\nThe backfill could not connect within 30 seconds.\n"
            "Backfill now uses its own session, so this is most likely a network "
            "issue. Check your internet connection and try again."
        )
        sys.exit(1)
    except Exception as exc:
        print(f"FAILED — {exc}")
        print("\nCould not connect to Telegram. Check your internet connection and try again.")
        sys.exit(1)

    if not await client.is_user_authorized():
        print("\nFirst-time backfill login (this uses a separate session, one time only).")
        print("Telegram will ask for your phone number and a login code.\n")
        await client.start()  # interactive; connection already established above
    print("connected.")

    db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # Resolve channel_ref: accept numeric ID or @username
    try:
        ref: int | str = int(channel_ref)
    except ValueError:
        ref = channel_ref  # treat as username

    try:
        entity = await asyncio.wait_for(client.get_entity(ref), timeout=30)
    except asyncio.TimeoutError:
        print(f"\nTimed out resolving channel '{channel_ref}'.")
        print("Telegram may be rate-limiting the request. Wait a minute and try again.")
        await client.disconnect()
        sys.exit(1)
    except Exception as exc:
        print(f"\nError resolving channel '{channel_ref}': {exc}")
        print("Make sure the channel ID is correct and your account is a member.")
        await client.disconnect()
        sys.exit(1)

    tg_id: int = entity.id
    name: str = getattr(entity, "title", None) or str(tg_id)
    username: str | None = getattr(entity, "username", None)
    member_count: int | None = getattr(entity, "participants_count", None)

    channel_row = _upsert_channel(db, tg_id, name, username, member_count)
    channel_id: str = channel_row["id"]

    print(f"\nBackfilling '{name}' — fetching last {limit} messages.")
    print("(Re-running is safe; messages already in the database are skipped.)\n")

    inserted = skipped = signal_count = 0
    last_signal_at = None

    # Progress threshold: print every message for small runs, every 10 otherwise
    _progress_every = 1 if limit <= 20 else (10 if limit <= 100 else 50)

    async for message in client.iter_messages(entity, limit=limit):
        if not message.date:
            continue

        posted_at = (
            message.date if message.date.tzinfo
            else message.date.replace(tzinfo=timezone.utc)
        )
        text: str | None = message.message or None
        has_img = _has_image(message)
        msg_type = classify_message(text, has_img)

        # Idempotent: skip if already stored
        existing = (
            db.table("messages")
            .select("id")
            .eq("channel_id", channel_id)
            .eq("telegram_message_id", message.id)
            .maybe_single()
            .execute()
            .data
        )
        if existing:
            skipped += 1
        else:
            msg_result = (
                db.table("messages")
                .insert({
                    "channel_id": channel_id,
                    "telegram_message_id": message.id,
                    "content": text,
                    "message_type": msg_type,
                    "source": "backfill",
                    "posted_at": posted_at.isoformat(),
                })
                .execute()
            )
            if not msg_result.data:
                logger.warning("Failed to insert message %s", message.id)
                continue

            msg_row = msg_result.data[0]
            inserted += 1

            if msg_type == "text_signal" and text:
                parsed = parse_text_signal(text)
                if parsed:
                    sig_existing = (
                        db.table("signals")
                        .select("id")
                        .eq("message_id", msg_row["id"])
                        .maybe_single()
                        .execute()
                        .data
                    )
                    if not sig_existing:
                        db.table("signals").insert({
                            "channel_id": channel_id,
                            "message_id": msg_row["id"],
                            "signal_type": parsed.signal_type,
                            "source": "backfill",
                            "direction": parsed.direction,
                            "entry": parsed.entry,
                            "entry_low": parsed.entry_low,
                            "entry_high": parsed.entry_high,
                            "stop_loss": parsed.stop_loss,
                            "take_profit_1": parsed.take_profit_1,
                            "take_profit_2": parsed.take_profit_2,
                            "take_profit_3": parsed.take_profit_3,
                            "raw_text": parsed.raw_text,
                            "posted_at": posted_at.isoformat(),
                            "confidence": parsed.confidence,
                            "parse_method": "regex",
                        }).execute()
                        signal_count += 1
                        if last_signal_at is None or posted_at > last_signal_at:
                            last_signal_at = posted_at

        total_processed = inserted + skipped
        if total_processed % _progress_every == 0:
            print(
                f"  {total_processed}/{limit} — "
                f"new: {inserted}  skipped: {skipped}  signals: {signal_count}"
            )

    # Update last_signal_at if we found any signals
    if last_signal_at:
        db.table("channels").update(
            {"last_signal_at": last_signal_at.isoformat()}
        ).eq("id", channel_id).execute()

    print(f"\nDone.")
    print(f"  Messages inserted : {inserted}")
    print(f"  Messages skipped  : {skipped}  (already in DB — safe to ignore)")
    print(f"  Signals parsed    : {signal_count}")
    if signal_count == 0:
        print(
            "\n  No signals found? This is normal if the channel posts chart images\n"
            "  rather than text. Run reprocess_images after backfill to classify those."
        )

    await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s — %(message)s",
    )

    parser = argparse.ArgumentParser(
        description="Backfill Telegram channel history into Supabase"
    )
    parser.add_argument(
        "--channel",
        required=True,
        help="Channel ID (e.g. -1001234567890) or @username",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Maximum number of messages to fetch (default: 500)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(backfill(args.channel, args.limit))
    except KeyboardInterrupt:
        print(
            "\n\nBackfill stopped. Nothing was corrupted.\n"
            "Re-running is safe — messages already imported are skipped automatically."
        )
        sys.exit(0)
