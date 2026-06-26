"""
list_channels.py — Phase 4 helper script.

Connects to Telegram as you (user-client) and prints all channels
you have joined, with their IDs. Run this once to identify which
channel IDs to add to your tracking list.

Usage:
    python scripts/list_channels.py
"""

import asyncio
import sys
from pathlib import Path

# Allow imports from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
import os

load_dotenv()


async def main():
    """Phase 4 implementation target."""
    raise NotImplementedError(
        "Implement in Phase 4 — requires TG_API_ID and TG_API_HASH in .env"
    )


if __name__ == "__main__":
    asyncio.run(main())
