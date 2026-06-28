"""
list_channels.py — list all Telegram channels and groups you've joined.

Run this once after setting TG_API_ID and TG_API_HASH in .env to find the
channel IDs you want to track. On first run, Telegram will ask for your phone
number and a 2FA code to create the session file.

Usage:
    python -m scripts.list_channels
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Suppress harmless Telethon "very new message" warnings — these appear for
# channels that use scheduled or system messages with large internal IDs.
logging.getLogger("telethon.client.updates").setLevel(logging.ERROR)
logging.getLogger("telethon").setLevel(logging.ERROR)

from dotenv import load_dotenv

load_dotenv()

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat

from backend.config import TG_API_ID, TG_API_HASH, TG_SESSION_NAME

# Always use an absolute path for the session file so it's found regardless
# of which directory you run this script from.
_PROJECT_ROOT = Path(__file__).parent.parent
_SESSION_PATH = str(_PROJECT_ROOT / TG_SESSION_NAME)


async def main() -> None:
    if not TG_API_ID or not TG_API_HASH:
        print("Error: TG_API_ID and TG_API_HASH must be set in .env")
        print("Get them at https://my.telegram.org → API development tools")
        sys.exit(1)

    client = TelegramClient(_SESSION_PATH, TG_API_ID, TG_API_HASH)
    print("Connecting to Telegram... ", end="", flush=True)
    try:
        await asyncio.wait_for(client.start(), timeout=30)
    except asyncio.TimeoutError:
        print("TIMED OUT")
        print(
            "\nCould not connect to Telegram within 30 seconds.\n"
            "Check your internet connection and try again."
        )
        sys.exit(1)
    print("connected.\n")

    print(f"{'ID':>22}  {'Type':<10}  {'Members':>8}  Name")
    print("-" * 72)

    channels: list[dict] = []

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, (Channel, Chat)):
            continue

        is_broadcast = isinstance(entity, Channel) and getattr(entity, "broadcast", False)
        kind = "channel" if is_broadcast else "group"
        members = getattr(entity, "participants_count", None)
        members_str = str(members) if members is not None else "?"

        print(f"{dialog.id:>22}  {kind:<10}  {members_str:>8}  {dialog.name}")
        channels.append({"id": dialog.id, "name": dialog.name, "type": kind})

    print(f"\nFound {len(channels)} channels/groups.")
    print("\nCopy the IDs you want to track and add them to .env:")
    print("  TRACKED_CHANNEL_IDS=-1001234567890,-1009876543210")

    await client.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
        sys.exit(0)
