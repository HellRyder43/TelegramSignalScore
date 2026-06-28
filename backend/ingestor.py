"""
Telegram ingestor — Phase 4 implementation.

Connects as a Telegram user-client via Telethon, listens for new messages,
edits, and deletes across tracked channels, and writes them to Supabase.

Run as a standalone process:
    python backend/ingestor.py
or import and call start_listener() from a FastAPI lifespan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from supabase import create_client, Client
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument

# Suppress harmless "Server sent a very new message" warnings that appear for
# channels using scheduled or system messages with large internal IDs.
logging.getLogger("telethon.client.updates").setLevel(logging.ERROR)

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    TG_API_ID,
    TG_API_HASH,
    TG_SESSION_NAME,
    TRACKED_CHANNEL_IDS,
    MT5_SYMBOL,
    ANTHROPIC_API_KEY,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    AI_QUALITY_ENABLED,
    AI_EDIT_ANALYSIS_ENABLED,
)
from backend.parser import classify_message, parse_text_signal, parse_signal_with_ai_fallback
from backend.notifier.base import Notifier

load_dotenv()

logger = logging.getLogger(__name__)

# ─── Module-level state ───────────────────────────────────────────────────────
# Populated in start_listener(); keyed by Telegram channel ID (signed int).
_db: Client | None = None
_channel_cache: dict[int, dict] = {}  # telegram_id → channels row
_notifier: Notifier | None = None


# ─── Utility helpers ──────────────────────────────────────────────────────────

def _has_image(message: Any) -> bool:
    """Return True if the Telethon message carries a photo or image document."""
    media = getattr(message, "media", None)
    if media is None:
        return False
    if isinstance(media, MessageMediaPhoto):
        return True
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc and getattr(doc, "mime_type", "").startswith("image/"):
            return True
    return False


def _get_image_mime(message: Any) -> str:
    """Return the MIME type of the image attached to a Telethon message."""
    media = getattr(message, "media", None)
    if isinstance(media, MessageMediaDocument):
        doc = getattr(media, "document", None)
        if doc:
            mime = getattr(doc, "mime_type", "")
            if mime.startswith("image/"):
                return mime
    return "image/jpeg"  # default for MessageMediaPhoto


def _parse_dt(value: str | datetime) -> datetime:
    """Parse an ISO datetime string or pass through a datetime, ensuring UTC tzinfo."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    s = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _detect_post_move_edit(
    direction: str,
    entry: float,
    posted_at: str | datetime,
    edited_at: datetime,
) -> bool:
    """
    Check whether price touched the entry level between post time and edit time.

    A True result means the channel likely edited signal levels *after* price
    had already filled the entry — a strong integrity red flag.
    Returns False silently if MT5 is unavailable or no candle data exists.
    """
    try:
        import MetaTrader5 as mt5  # type: ignore

        # _parse_dt returns UTC-aware datetimes; strip tzinfo for MT5 C-extension.
        start = _parse_dt(posted_at).astimezone(timezone.utc).replace(tzinfo=None)
        end = _parse_dt(edited_at).astimezone(timezone.utc).replace(tzinfo=None)

        if not mt5.initialize():
            logger.debug("MT5 not available for post-move check")
            return False

        rates = mt5.copy_rates_range(MT5_SYMBOL, mt5.TIMEFRAME_M1, start, end)
        if rates is None or len(rates) == 0:
            return False

        for r in rates:
            if direction == "BUY" and float(r["low"]) <= entry:
                return True
            if direction == "SELL" and float(r["high"]) >= entry:
                return True

        return False
    except Exception as exc:
        logger.debug("Post-move MT5 check failed (non-fatal): %s", exc)
        return False


# ─── DB helpers (all sync; call via asyncio.to_thread) ───────────────────────

def _db_ensure_channel(tg_id: int, name: str, username: str | None, member_count: int | None) -> dict | None:
    assert _db is not None
    existing = (
        _db.table("channels")
        .select("*")
        .eq("telegram_id", tg_id)
        .maybe_single()
        .execute()
        .data
    )
    if existing:
        return existing
    result = (
        _db.table("channels")
        .insert({"telegram_id": tg_id, "name": name, "username": username, "member_count": member_count})
        .execute()
    )
    return result.data[0] if result.data else None


def _db_resolve_channel_uuid(tg_id: int) -> str | None:
    """Resolve a Telegram channel ID to our internal channel UUID.

    Checks the in-memory cache first, then falls back to a DB lookup (caching the
    result). Returns None if we have never recorded this channel — callers must
    treat None as "cannot scope safely" and skip, never run an unscoped query.
    Telegram message IDs are unique only *within* a channel, so an unscoped
    edit/delete could corrupt a different channel's data and trust score.
    """
    assert _db is not None
    cached = _channel_cache.get(tg_id)
    if cached:
        return cached["id"]
    row = (
        _db.table("channels")
        .select("*")
        .eq("telegram_id", tg_id)
        .maybe_single()
        .execute()
        .data
    )
    if row:
        _channel_cache[tg_id] = row
        return row["id"]
    return None


def _db_get_or_insert_message(
    channel_id: str,
    tg_msg_id: int,
    content: str | None,
    msg_type: str,
    source: str,
    posted_at: datetime,
) -> dict | None:
    assert _db is not None
    existing = (
        _db.table("messages")
        .select("id, content, channel_id, message_type")
        .eq("channel_id", channel_id)
        .eq("telegram_message_id", tg_msg_id)
        .maybe_single()
        .execute()
        .data
    )
    if existing:
        return existing
    result = (
        _db.table("messages")
        .insert({
            "channel_id": channel_id,
            "telegram_message_id": tg_msg_id,
            "content": content,
            "message_type": msg_type,
            "source": source,
            "posted_at": posted_at.isoformat(),
        })
        .execute()
    )
    return result.data[0] if result.data else None


def _db_insert_signal(
    channel_id: str,
    message_id: str,
    parsed: Any,
    source: str,
    posted_at: datetime,
    parse_method: str = "regex",
) -> dict | None:
    assert _db is not None
    # Idempotency guard: a live NewMessage event can be redelivered (reconnect,
    # gap-fill). The signals table has no UNIQUE(message_id), so without this a
    # redelivery would create a second signal row for the same post — double-
    # counting it in the trust score and re-firing the Discord alert. Returning
    # None here makes the caller skip the alert/scoring path (same as backfill's
    # sig_existing check). For a hard guarantee, a UNIQUE(message_id) constraint
    # on signals would also catch the rare concurrent-event race.
    existing = (
        _db.table("signals")
        .select("id")
        .eq("message_id", message_id)
        .maybe_single()
        .execute()
        .data
    )
    if existing:
        logger.info("Signal already exists for message %s — skipping duplicate insert", message_id)
        return None
    result = (
        _db.table("signals")
        .insert({
            "channel_id": channel_id,
            "message_id": message_id,
            "signal_type": parsed.signal_type,
            "source": source,
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
            "parse_method": parse_method,
        })
        .execute()
    )
    return result.data[0] if result.data else None


def _db_update_last_signal(channel_id: str, posted_at: datetime) -> None:
    assert _db is not None
    _db.table("channels").update({"last_signal_at": posted_at.isoformat()}).eq("id", channel_id).execute()


def _db_insert_screenshot_claim(
    channel_id: str,
    message_id: str,
    claim: Any,          # ScreenshotData — typed as Any to avoid circular import at module level
    verdict: str,
    notes: str | None,
    posted_at: datetime,
) -> dict | None:
    assert _db is not None
    result = (
        _db.table("screenshot_claims").insert({
            "channel_id": channel_id,
            "message_id": message_id,
            "claimed_direction": claim.direction,
            "claimed_open": claim.open_price,
            "claimed_close": claim.close_price,
            "claimed_profit_pts": claim.profit_pts,
            "claimed_open_time": claim.open_time,
            "claimed_close_time": claim.close_time,
            "verdict": verdict,
            "posted_at": posted_at.isoformat(),
            "notes": notes,
        }).execute()
    )
    return result.data[0] if result.data else None


def _db_update_screenshot_counts(channel_id: str, verdict: str) -> None:
    assert _db is not None
    ch = (
        _db.table("channels")
        .select("screenshot_confirmed, screenshot_contradicted")
        .eq("id", channel_id)
        .maybe_single()
        .execute()
        .data
    )
    if ch is None:
        return
    if verdict == "confirmed":
        _db.table("channels").update(
            {"screenshot_confirmed": ch["screenshot_confirmed"] + 1}
        ).eq("id", channel_id).execute()
    elif verdict == "contradicted":
        _db.table("channels").update(
            {"screenshot_contradicted": ch["screenshot_contradicted"] + 1}
        ).eq("id", channel_id).execute()


def _db_lookup_message_for_edit(tg_msg_id: int, channel_uuid: str) -> tuple[dict | None, str, dict | None]:
    """
    Returns (msg_row, content_before, signal_row_or_None).
    content_before is the text as of the last known state (original or last edit).

    Scoped by channel_uuid: telegram_message_id is unique only within a channel
    (messages has UNIQUE(channel_id, telegram_message_id)), so an unscoped lookup
    could match and attribute the edit to a different channel's message.
    """
    assert _db is not None
    rows = (
        _db.table("messages")
        .select("id, content, channel_id, message_type")
        .eq("telegram_message_id", tg_msg_id)
        .eq("channel_id", channel_uuid)
        .execute()
        .data
    )
    if not rows:
        return None, "", None

    msg_row = rows[0]

    # content_before = latest edit's content_after, or original messages.content
    edits = (
        _db.table("message_edits")
        .select("edit_number, content_after")
        .eq("message_id", msg_row["id"])
        .order("edit_number", desc=True)
        .limit(1)
        .execute()
        .data
    )
    content_before = edits[0]["content_after"] if edits else (msg_row["content"] or "")

    sig_rows = (
        _db.table("signals")
        .select("direction, entry, posted_at")
        .eq("message_id", msg_row["id"])
        .limit(1)
        .execute()
        .data
    )
    sig = sig_rows[0] if sig_rows else None

    return msg_row, content_before, sig


def _db_record_edit(
    message_id: str,
    channel_id: str,
    content_before: str,
    content_after: str,
    edited_at: datetime,
    is_post_move: bool,
) -> None:
    assert _db is not None
    # Determine next edit number
    rows = (
        _db.table("message_edits")
        .select("edit_number")
        .eq("message_id", message_id)
        .order("edit_number", desc=True)
        .limit(1)
        .execute()
        .data
    )
    next_num = (rows[0]["edit_number"] + 1) if rows else 1

    _db.table("message_edits").insert({
        "message_id": message_id,
        "channel_id": channel_id,
        "edit_number": next_num,
        "content_before": content_before,
        "content_after": content_after,
        "edited_at": edited_at.isoformat(),
        "is_post_move_edit": is_post_move,
    }).execute()

    # Increment channel edit_count
    ch = _db.table("channels").select("edit_count").eq("id", channel_id).maybe_single().execute().data
    if ch is not None:
        _db.table("channels").update({"edit_count": ch["edit_count"] + 1}).eq("id", channel_id).execute()

    return next_num


def _db_save_quality_assessment(signal_id: str, assessment: Any) -> None:
    assert _db is not None
    _db.table("signal_quality_assessments").upsert({
        "signal_id": signal_id,
        "quality_score": assessment.quality_score,
        "is_retrospective": assessment.is_retrospective,
        "flags": assessment.flags,
        "explanation": assessment.explanation,
    }, on_conflict="signal_id").execute()


def _db_update_edit_ai_analysis(message_id: str, edit_number: int, analysis: Any) -> None:
    assert _db is not None
    from datetime import datetime, timezone
    _db.table("message_edits").update({
        "ai_intent": analysis.intent,
        "ai_suspicion_score": analysis.suspicion_score,
        "ai_intent_notes": analysis.notes,
        "ai_assessed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("message_id", message_id).eq("edit_number", edit_number).execute()


def _db_mark_deleted(tg_msg_id: int, channel_uuid: str) -> list[str]:
    """Mark messages deleted within a specific channel. Returns UUIDs of messages
    that were text_signals (for Discord follow-ups).

    channel_uuid is required and the query is always channel-scoped: Telegram
    message IDs are unique only within a channel, so an unscoped match could mark
    a same-numbered message in a different channel as deleted and unjustly inflate
    that channel's delete_count / lower its trust score.
    """
    assert _db is not None
    rows = (
        _db.table("messages")
        .select("id, channel_id, message_type")
        .eq("telegram_message_id", tg_msg_id)
        .eq("channel_id", channel_uuid)
        .execute()
        .data
    )

    signal_message_ids: list[str] = []
    for row in rows:
        _db.table("messages").update({"is_deleted": True}).eq("id", row["id"]).execute()

        if row["message_type"] == "text_signal":
            signal_message_ids.append(row["id"])
            ch = _db.table("channels").select("delete_count").eq("id", row["channel_id"]).maybe_single().execute().data
            if ch is not None:
                _db.table("channels").update({"delete_count": ch["delete_count"] + 1}).eq("id", row["channel_id"]).execute()

    return signal_message_ids


def _db_get_discord_message_id(message_uuid: str) -> str | None:
    """Look up the Discord message ID for a signal alert by its internal messages.id."""
    assert _db is not None
    rows = (
        _db.table("discord_alerts")
        .select("discord_message_id")
        .eq("message_id", message_uuid)
        .eq("alert_type", "signal")
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["discord_message_id"] if rows else None


# ─── Event handlers ───────────────────────────────────────────────────────────

async def _on_new_message(event: events.NewMessage.Event, notifier: Notifier | None) -> None:
    tg_id: int = event.chat_id
    if TRACKED_CHANNEL_IDS and tg_id not in TRACKED_CHANNEL_IDS:
        return

    # Resolve channel entity (name, username, member count)
    try:
        chat = await event.get_chat()
        name: str = getattr(chat, "title", None) or str(tg_id)
        username: str | None = getattr(chat, "username", None)
        member_count: int | None = getattr(chat, "participants_count", None)
    except Exception as exc:
        logger.warning("Could not resolve chat %s: %s", tg_id, exc)
        name, username, member_count = str(tg_id), None, None

    channel_row = await asyncio.to_thread(_db_ensure_channel, tg_id, name, username, member_count)
    if not channel_row:
        logger.error("Failed to upsert channel %s", tg_id)
        return
    _channel_cache[tg_id] = channel_row

    msg = event.message
    text: str | None = msg.message or None
    has_img = _has_image(msg)
    img_bytes: bytes | None = None
    img_mime: str = "image/jpeg"

    # Initial text-based classification
    msg_type = classify_message(text, has_img)

    # Vision classification: when we have an image and the Anthropic key is set,
    # run the fine-grained classifier to distinguish zone_image from mt5_screenshot.
    if msg_type == "zone_image":
        img_mime = _get_image_mime(msg)
        img_bytes = await msg.download_media(bytes)
        if img_bytes:
            from backend.vision.classifier import classify_image
            try:
                image_class = await asyncio.to_thread(classify_image, img_bytes, img_mime)
                if image_class == "mt5_screenshot":
                    msg_type = "mt5_screenshot"
                elif image_class != "chart_zone":
                    msg_type = "non_signal"
                # "chart_zone" → stays "zone_image"
            except Exception as exc:
                logger.warning("Vision classify failed, deferring image: %s", exc)
                msg_type = "image_deferred"
        else:
            logger.warning("Could not download image for msg=%s, deferring", msg.id)
            msg_type = "image_deferred"

    posted_at = msg.date if msg.date.tzinfo else msg.date.replace(tzinfo=timezone.utc)

    msg_row = await asyncio.to_thread(
        _db_get_or_insert_message,
        channel_row["id"], msg.id, text, msg_type, "live", posted_at,
    )
    if not msg_row:
        logger.error("Failed to insert message tg=%s msg=%s", tg_id, msg.id)
        return

    logger.info("[%s] msg=%s type=%s", name, msg.id, msg_type)

    # ── Text signal ───────────────────────────────────────────────────────────
    if msg_type == "text_signal" and text:
        parsed, parse_method = parse_signal_with_ai_fallback(text)
        if parsed:
            signal_row = await asyncio.to_thread(
                _db_insert_signal,
                channel_row["id"], msg_row["id"], parsed, "live", posted_at, parse_method,
            )
            if signal_row:
                await asyncio.to_thread(_db_update_last_signal, channel_row["id"], posted_at)
                if notifier:
                    try:
                        await notifier.send_signal_alert(signal_row, channel_row)
                    except Exception as exc:
                        logger.warning("Discord alert failed (non-fatal): %s", exc)
                if AI_QUALITY_ENABLED and ANTHROPIC_API_KEY:
                    try:
                        from backend.ai.quality_assessor import assess_signal_quality
                        qa = await asyncio.to_thread(assess_signal_quality, parsed.raw_text)
                        if qa:
                            await asyncio.to_thread(_db_save_quality_assessment, signal_row["id"], qa)
                    except Exception as exc:
                        logger.warning("Quality assessment failed (non-fatal): %s", exc)

    # ── Zone image (chart with entry zone) ────────────────────────────────────
    elif msg_type == "zone_image":
        if img_bytes:
            from backend.vision.chart_parser import parse_chart_zone
            try:
                parsed = await asyncio.to_thread(parse_chart_zone, img_bytes, text, img_mime)
            except Exception as exc:
                logger.warning("Chart zone parse failed for msg=%s: %s", msg.id, exc)
                parsed = None
            if parsed:
                signal_row = await asyncio.to_thread(
                    _db_insert_signal,
                    channel_row["id"], msg_row["id"], parsed, "live", posted_at, "vision",
                )
                if signal_row:
                    await asyncio.to_thread(_db_update_last_signal, channel_row["id"], posted_at)
                    if notifier:
                        try:
                            await notifier.send_signal_alert(signal_row, channel_row)
                        except Exception as exc:
                            logger.warning("Discord alert failed (non-fatal): %s", exc)
                    if AI_QUALITY_ENABLED and ANTHROPIC_API_KEY:
                        try:
                            from backend.ai.quality_assessor import assess_signal_quality
                            qa = await asyncio.to_thread(assess_signal_quality, parsed.raw_text or text or "")
                            if qa:
                                await asyncio.to_thread(_db_save_quality_assessment, signal_row["id"], qa)
                        except Exception as exc:
                            logger.warning("Quality assessment failed (non-fatal): %s", exc)

    # ── MT5 profit screenshot ─────────────────────────────────────────────────
    elif msg_type == "mt5_screenshot":
        if img_bytes:
            from backend.vision.screenshot_parser import parse_mt5_screenshot
            from backend.vision.screenshot_checker import cross_check_screenshot
            try:
                claim = await asyncio.to_thread(parse_mt5_screenshot, img_bytes, img_mime)
            except Exception as exc:
                logger.warning("Screenshot parse failed for msg=%s: %s", msg.id, exc)
                claim = None
            if claim:
                verdict, notes = await asyncio.to_thread(
                    cross_check_screenshot, claim, MT5_SYMBOL
                )
                logger.info("[%s] screenshot msg=%s verdict=%s", name, msg.id, verdict)
                await asyncio.to_thread(
                    _db_insert_screenshot_claim,
                    channel_row["id"], msg_row["id"], claim, verdict, notes, posted_at,
                )
                await asyncio.to_thread(_db_update_screenshot_counts, channel_row["id"], verdict)


async def _on_edited_message(event: events.MessageEdited.Event) -> None:
    tg_id: int = event.chat_id
    if TRACKED_CHANNEL_IDS and tg_id not in TRACKED_CHANNEL_IDS:
        return

    msg = event.message
    new_text: str = msg.message or ""
    edited_at: datetime = (msg.edit_date or datetime.now(timezone.utc))
    if edited_at.tzinfo is None:
        edited_at = edited_at.replace(tzinfo=timezone.utc)

    channel_uuid = await asyncio.to_thread(_db_resolve_channel_uuid, tg_id)
    if not channel_uuid:
        logger.warning("[edit] unknown channel tg=%s msg=%s — skipping (cannot scope safely)", tg_id, msg.id)
        return

    msg_row, content_before, sig = await asyncio.to_thread(
        _db_lookup_message_for_edit, msg.id, channel_uuid
    )
    if not msg_row:
        return  # Not a tracked message; ignore
    if content_before == new_text:
        return  # Media-only edit or no text change

    # Check if price had already filled the entry before this edit
    is_post_move = False
    if sig and sig.get("entry") and sig.get("direction"):
        is_post_move = await asyncio.to_thread(
            _detect_post_move_edit,
            sig["direction"],
            float(sig["entry"]),
            sig["posted_at"],
            edited_at,
        )

    edit_num = await asyncio.to_thread(
        _db_record_edit,
        msg_row["id"], msg_row["channel_id"],
        content_before, new_text, edited_at, is_post_move,
    )
    logger.info("[edit] msg=%s post_move=%s", msg.id, is_post_move)

    if AI_EDIT_ANALYSIS_ENABLED and ANTHROPIC_API_KEY and edit_num:
        try:
            from backend.ai.edit_analyzer import analyze_edit_intent
            analysis = await asyncio.to_thread(
                analyze_edit_intent, content_before, new_text, is_post_move
            )
            if analysis:
                await asyncio.to_thread(
                    _db_update_edit_ai_analysis, msg_row["id"], edit_num, analysis
                )
        except Exception as exc:
            logger.warning("Edit AI analysis failed (non-fatal): %s", exc)

    # Discord edit follow-up — only for text_signals that have an existing alert
    if _notifier and msg_row.get("message_type") == "text_signal":
        discord_msg_id = await asyncio.to_thread(_db_get_discord_message_id, msg_row["id"])
        if discord_msg_id:
            try:
                await _notifier.send_edit_followup(discord_msg_id, content_before, new_text, edited_at)
            except Exception as exc:
                logger.warning("Discord edit follow-up failed (non-fatal): %s", exc)


async def _on_deleted_message(event: events.MessageDeleted.Event) -> None:
    if not event.deleted_ids:
        return

    chat_id: int | None = getattr(event, "chat_id", None)
    if chat_id is None:
        # Without a chat_id we cannot tell which channel these IDs belong to, and
        # Telegram message IDs are not globally unique — an unscoped delete could
        # wrongly flag another channel's messages. Skip rather than corrupt data.
        logger.warning("[delete] event has no chat_id — skipping %d id(s)", len(event.deleted_ids))
        return
    if TRACKED_CHANNEL_IDS and chat_id not in TRACKED_CHANNEL_IDS:
        return

    # Resolve our UUID for this channel (cache, then DB). Bail if unknown so the
    # delete is always channel-scoped.
    channel_uuid = await asyncio.to_thread(_db_resolve_channel_uuid, chat_id)
    if not channel_uuid:
        logger.warning("[delete] unknown channel tg=%s — skipping %d id(s)", chat_id, len(event.deleted_ids))
        return

    for tg_msg_id in event.deleted_ids:
        signal_msg_ids = await asyncio.to_thread(_db_mark_deleted, tg_msg_id, channel_uuid)
        logger.info("[delete] msg=%s channel=%s", tg_msg_id, chat_id)

        if _notifier and signal_msg_ids:
            for msg_uuid in signal_msg_ids:
                discord_msg_id = await asyncio.to_thread(_db_get_discord_message_id, msg_uuid)
                if discord_msg_id:
                    try:
                        await _notifier.send_delete_followup(discord_msg_id)
                    except Exception as exc:
                        logger.warning("Discord delete follow-up failed (non-fatal): %s", exc)


# ─── Entry point ──────────────────────────────────────────────────────────────

async def start_listener(notifier: Notifier | None = None) -> None:
    """
    Connect as a Telegram user-client and listen indefinitely.

    Writes all messages from tracked channels to Supabase in real time.
    notifier: optional Notifier for Discord alerts (wired in Phase 6).
    """
    global _db, _notifier

    if not TG_API_ID or not TG_API_HASH:
        raise RuntimeError("TG_API_ID and TG_API_HASH must be set in .env")
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")

    _db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # Auto-create Discord notifier if caller didn't provide one
    if notifier is None and DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID:
        from backend.notifier.discord_bot import DiscordNotifier
        notifier = DiscordNotifier(_db)
        logger.info("Discord notifier auto-initialized")
    _notifier = notifier

    # Pre-populate channel cache so delete events can resolve UUIDs without a DB hit
    def _load():
        return _db.table("channels").select("*").execute().data  # type: ignore[union-attr]

    for row in await asyncio.to_thread(_load):
        _channel_cache[row["telegram_id"]] = row
    logger.info("Channel cache loaded (%d channels)", len(_channel_cache))

    if not TRACKED_CHANNEL_IDS:
        logger.warning(
            "TRACKED_CHANNEL_IDS is not set — no messages will be processed. "
            "Run `python scripts/list_channels.py` to find IDs, then set TRACKED_CHANNEL_IDS in .env."
        )
    else:
        logger.info("Tracking %d channel(s): %s", len(TRACKED_CHANNEL_IDS), TRACKED_CHANNEL_IDS)

    _session_path = str(Path(__file__).parent.parent / TG_SESSION_NAME)
    client = TelegramClient(_session_path, TG_API_ID, TG_API_HASH)

    @client.on(events.NewMessage())
    async def _(ev: events.NewMessage.Event) -> None:
        try:
            await _on_new_message(ev, notifier)
        except Exception as exc:
            logger.error("Unhandled error in new-message handler: %s", exc, exc_info=True)

    @client.on(events.MessageEdited())
    async def _(ev: events.MessageEdited.Event) -> None:
        try:
            await _on_edited_message(ev)
        except Exception as exc:
            logger.error("Unhandled error in edit handler: %s", exc, exc_info=True)

    @client.on(events.MessageDeleted())
    async def _(ev: events.MessageDeleted.Event) -> None:
        try:
            await _on_deleted_message(ev)
        except Exception as exc:
            logger.error("Unhandled error in delete handler: %s", exc, exc_info=True)

    await client.start()
    logger.info("Telegram ingestor running. Press Ctrl-C to stop.")
    await client.run_until_disconnected()

    if _notifier:
        await _notifier.close()


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        stream=sys.stdout,
    )
    asyncio.run(start_listener())
