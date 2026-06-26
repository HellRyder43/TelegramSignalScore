"""
Discord notifier — Phase 6 implementation target.
"""

from __future__ import annotations
from .base import Notifier


class DiscordNotifier(Notifier):
    """
    Sends signal alerts and threaded follow-ups via a Discord bot.
    Phase 6 implementation.
    """

    async def send_signal_alert(self, signal: dict, channel: dict) -> str:
        raise NotImplementedError("Implement in Phase 6")

    async def send_edit_followup(self, alert_message_id: str, before: str, after: str, edited_at) -> None:
        raise NotImplementedError("Implement in Phase 6")

    async def send_delete_followup(self, alert_message_id: str) -> None:
        raise NotImplementedError("Implement in Phase 6")

    async def send_resolution_followup(self, alert_message_id: str, outcome: str, points: float | None) -> None:
        raise NotImplementedError("Implement in Phase 6")
