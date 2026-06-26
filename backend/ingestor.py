"""
Telegram ingestor — Phase 4 implementation target.

Connects as a Telegram user-client via Telethon, listens for new messages,
edits, and deletes, and writes them to Supabase.
"""

from __future__ import annotations


async def start_listener() -> None:
    """
    Start the Telethon user-client and register event handlers for:
      - NewMessage: write to messages, classify, trigger parser
      - MessageEdited: append to message_edits (never overwrite), flag integrity
      - MessageDeleted: mark is_deleted=TRUE in messages, flag integrity
    Phase 4 implementation.
    """
    raise NotImplementedError("Implement in Phase 4")
