"""
Discord notifier — Phase 6 implementation.

Uses discord.py's REST API only (no gateway/websocket) for minimal resource
usage. De-duplication and follow-up thread IDs are coordinated via the
discord_alerts Supabase table so both the ingestor and the API process can
share the same alert state without needing a shared Python object.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import discord
from supabase import Client

from backend.config import DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID
from .base import Notifier

logger = logging.getLogger(__name__)

VERDICT_COLORS: dict[str, int] = {
    "trusted": 0x16A34A,   # green-600
    "caution": 0xD97706,   # amber-600
    "observe": 0xEA580C,   # orange-600
    "avoid":   0xDC2626,   # red-600
}


class DiscordNotifier(Notifier):
    """
    Sends signal alerts and threaded follow-ups via a Discord bot.

    Lazy-initializes: the Discord client logs in on the first notification call,
    not at construction time, so callers don't need to await anything up front.
    """

    def __init__(self, db: Client) -> None:
        self._db = db
        self._client: discord.Client | None = None
        self._channel: discord.TextChannel | None = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def _ensure_ready(self) -> discord.TextChannel:
        """Lazily log in and fetch the target channel (REST only, no gateway)."""
        if not DISCORD_BOT_TOKEN:
            raise RuntimeError("DISCORD_BOT_TOKEN is not set in .env")
        if not DISCORD_CHANNEL_ID:
            raise RuntimeError("DISCORD_CHANNEL_ID is not set in .env")

        if self._client is None:
            self._client = discord.Client(intents=discord.Intents.none())
            await self._client.login(DISCORD_BOT_TOKEN)

        if self._channel is None:
            ch = await self._client.fetch_channel(DISCORD_CHANNEL_ID)
            if not isinstance(ch, discord.TextChannel):
                raise RuntimeError(
                    f"DISCORD_CHANNEL_ID {DISCORD_CHANNEL_ID} is not a text channel "
                    f"(got {type(ch).__name__})"
                )
            self._channel = ch

        return self._channel

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._channel = None

    # ── Async DB wrappers (sync Supabase → asyncio.to_thread) ────────────────

    async def _db_check_dedup(self, signal_id: str) -> str | None:
        def _do() -> str | None:
            rows = (
                self._db.table("discord_alerts")
                .select("discord_message_id")
                .eq("signal_id", signal_id)
                .eq("alert_type", "signal")
                .limit(1)
                .execute()
                .data
            )
            return rows[0]["discord_message_id"] if rows else None
        return await asyncio.to_thread(_do)

    async def _db_store_alert(
        self, signal_id: str | None, message_id: str | None, discord_msg_id: str
    ) -> None:
        def _do() -> None:
            self._db.table("discord_alerts").insert({
                "signal_id": signal_id,
                "message_id": message_id,
                "discord_message_id": discord_msg_id,
                "alert_type": "signal",
            }).execute()
        await asyncio.to_thread(_do)

    async def _db_get_alert_row(self, discord_message_id: str) -> dict | None:
        def _do() -> dict | None:
            rows = (
                self._db.table("discord_alerts")
                .select("id, discord_thread_id")
                .eq("discord_message_id", discord_message_id)
                .eq("alert_type", "signal")
                .limit(1)
                .execute()
                .data
            )
            return rows[0] if rows else None
        return await asyncio.to_thread(_do)

    async def _db_set_thread_id(self, discord_message_id: str, thread_id: str) -> None:
        def _do() -> None:
            self._db.table("discord_alerts").update(
                {"discord_thread_id": thread_id}
            ).eq("discord_message_id", discord_message_id).execute()
        await asyncio.to_thread(_do)

    # ── Thread management ─────────────────────────────────────────────────────

    async def _get_or_create_thread(
        self, discord_message_id: str
    ) -> discord.Thread | None:
        """
        Return the follow-up thread for an alert, creating it on the first call.
        Returns None on failure; callers fall back to posting directly in channel.
        """
        await self._ensure_ready()

        alert_row = await self._db_get_alert_row(discord_message_id)
        if not alert_row:
            return None

        thread_id = alert_row.get("discord_thread_id")
        if thread_id:
            try:
                ch = await self._client.fetch_channel(int(thread_id))  # type: ignore[union-attr]
                if isinstance(ch, discord.Thread):
                    return ch
            except discord.NotFound:
                pass  # Thread deleted or archived — create a new one below
            except Exception as exc:
                logger.warning("Failed to fetch thread %s: %s", thread_id, exc)
                return None

        # Create a new thread from the original alert message
        try:
            orig_msg = await self._channel.fetch_message(int(discord_message_id))  # type: ignore[union-attr]
            thread = await orig_msg.create_thread(
                name="Signal updates",
                auto_archive_duration=10080,  # 7 days
            )
            await self._db_set_thread_id(discord_message_id, str(thread.id))
            return thread
        except Exception as exc:
            logger.warning(
                "Could not create Discord thread (will post to channel): %s", exc
            )
            return None

    # ── Embed builders ────────────────────────────────────────────────────────

    def _parse_ts(self, ts: object) -> datetime | None:
        if ts is None:
            return None
        if isinstance(ts, datetime):
            return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _build_signal_embed(self, signal: dict, channel: dict) -> discord.Embed:
        verdict = channel.get("verdict", "observe")
        color = VERDICT_COLORS.get(verdict, 0x6B7280)
        direction = signal.get("direction", "?")
        prefix = "🟢 BUY" if direction == "BUY" else "🔴 SELL"

        embed = discord.Embed(title=f"{prefix} XAUUSD", color=color)
        embed.set_author(name=channel.get("name", "Unknown channel"))

        entry = signal.get("entry")
        entry_low = signal.get("entry_low")
        entry_high = signal.get("entry_high")
        if entry is not None:
            embed.add_field(name="Entry", value=f"{float(entry):.2f}", inline=True)
        elif entry_low is not None and entry_high is not None:
            embed.add_field(
                name="Zone",
                value=f"{float(entry_low):.2f} – {float(entry_high):.2f}",
                inline=True,
            )

        sl = signal.get("stop_loss")
        embed.add_field(
            name="SL",
            value=f"{float(sl):.2f}" if sl is not None else "—",
            inline=True,
        )

        tp_lines = []
        for label, key in [
            ("TP1", "take_profit_1"),
            ("TP2", "take_profit_2"),
            ("TP3", "take_profit_3"),
        ]:
            val = signal.get(key)
            if val is not None:
                tp_lines.append(f"{label}: {float(val):.2f}")
        embed.add_field(name="TP", value="\n".join(tp_lines) if tp_lines else "—", inline=True)

        score = channel.get("trust_score", 0)
        embed.set_footer(text=f"Trust Score {score}/100 · {verdict.title()}")

        ts = self._parse_ts(signal.get("posted_at"))
        if ts:
            embed.timestamp = ts

        return embed

    # ── Notifier interface ────────────────────────────────────────────────────

    async def send_signal_alert(self, signal: dict, channel: dict) -> str:
        signal_id: str | None = signal.get("id")
        message_id: str | None = signal.get("message_id")

        # De-dupe: never fire the same signal alert twice
        if signal_id:
            existing = await self._db_check_dedup(signal_id)
            if existing:
                return existing

        ch = await self._ensure_ready()
        embed = self._build_signal_embed(signal, channel)
        msg = await ch.send(embed=embed)
        discord_msg_id = str(msg.id)

        await self._db_store_alert(signal_id, message_id, discord_msg_id)
        return discord_msg_id

    async def send_edit_followup(
        self, alert_message_id: str, before: str, after: str, edited_at: object
    ) -> None:
        thread = await self._get_or_create_thread(alert_message_id)
        dest: discord.TextChannel | discord.Thread = thread or await self._ensure_ready()

        embed = discord.Embed(title="⚠️ Signal levels changed", color=0xD97706)
        embed.add_field(name="Before", value=f"```\n{before[:900]}\n```", inline=False)
        embed.add_field(name="After", value=f"```\n{after[:900]}\n```", inline=False)

        ts = self._parse_ts(edited_at)
        if ts:
            embed.timestamp = ts

        await dest.send(embed=embed)

    async def send_delete_followup(self, alert_message_id: str) -> None:
        thread = await self._get_or_create_thread(alert_message_id)
        dest: discord.TextChannel | discord.Thread = thread or await self._ensure_ready()

        embed = discord.Embed(
            title="🗑️ Signal deleted",
            description="The original Telegram message was deleted by the channel admin.",
            color=0xDC2626,
        )
        await dest.send(embed=embed)

    async def send_resolution_followup(
        self, alert_message_id: str, outcome: str, points: float | None
    ) -> None:
        thread = await self._get_or_create_thread(alert_message_id)
        dest: discord.TextChannel | discord.Thread = thread or await self._ensure_ready()

        pts_str = ""
        if points is not None:
            sign = "+" if points >= 0 else ""
            pts_str = f" {sign}{points:.0f} pts"

        if outcome == "win":
            title, color, footer = f"✅ Win{pts_str}", 0x16A34A, None
        elif outcome == "loss":
            title, color, footer = f"❌ Loss{pts_str}", 0xDC2626, None
        elif outcome == "ambiguous_loss":
            title = f"⚠️ Ambiguous loss{pts_str}"
            color = 0xD97706
            footer = "Single candle spanned both SL and TP — resolved conservatively as a loss."
        else:
            title = f"ℹ️ {outcome.replace('_', ' ').title()}{pts_str}"
            color, footer = 0x6B7280, None

        embed = discord.Embed(title=title, color=color)
        if footer:
            embed.set_footer(text=footer)

        await dest.send(embed=embed)
