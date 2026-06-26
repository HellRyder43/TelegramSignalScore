"""
backfill.py — Phase 4 helper script.

Pulls historical messages from a Telegram channel and writes them to
Supabase with source='backfill'. Backfilled signals are weighted less
in scoring than live signals.

Usage:
    python scripts/backfill.py --channel <channel_id> --limit 500
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main():
    """Phase 4 implementation target."""
    raise NotImplementedError("Implement in Phase 4")


if __name__ == "__main__":
    asyncio.run(main())
