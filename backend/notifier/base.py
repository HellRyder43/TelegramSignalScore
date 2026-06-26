"""
Notifier interface — Phase 6 implementation target.

All notification channels implement this base class so the pipeline
is not coupled to Discord specifically.
"""

from __future__ import annotations
from abc import ABC, abstractmethod


class Notifier(ABC):

    @abstractmethod
    async def send_signal_alert(self, signal: dict, channel: dict) -> str:
        """Send a forward-signal alert. Returns the platform message ID."""

    @abstractmethod
    async def send_edit_followup(self, alert_message_id: str, before: str, after: str, edited_at) -> None:
        """Post an edit follow-up under the original alert."""

    @abstractmethod
    async def send_delete_followup(self, alert_message_id: str) -> None:
        """Post a deletion notice under the original alert."""

    @abstractmethod
    async def send_resolution_followup(self, alert_message_id: str, outcome: str, points: float | None) -> None:
        """Post the verified outcome under the original alert."""
