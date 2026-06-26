"""
FastAPI application — Phase 3 implementation.
"""

from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    VERIFY_INTERVAL_SECS,
    MT5_SYMBOL,
)
from backend.verifier import verify_signal, MT5NotConnectedError, EntryNeverFilledError
from backend.scorer import compute_trust_score

logger = logging.getLogger(__name__)

# ─── Supabase client ──────────────────────────────────────────────────────────

def _make_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ─── Verification pass ────────────────────────────────────────────────────────

def _run_verification_pass(db: Client) -> int:
    """Resolve all unresolved signals. Returns number of signals processed."""
    rows = (
        db.table("signals")
        .select("id, channel_id, direction, entry, stop_loss, take_profit_1, posted_at")
        .eq("resolution_status", "unresolved")
        .execute()
        .data
    )

    if not rows:
        return 0

    affected_channels: set[str] = set()

    for sig in rows:
        try:
            result = verify_signal(
                direction=sig["direction"],
                entry=float(sig["entry"]),
                stop_loss=float(sig["stop_loss"]),
                take_profit=float(sig["take_profit_1"]),
                posted_at=sig["posted_at"],
                symbol=MT5_SYMBOL,
            )

            if result.outcome == "unresolved":
                continue

            db.table("signal_outcomes").upsert(
                {
                    "signal_id": sig["id"],
                    "outcome": result.outcome,
                    "points": result.points,
                    "candles_walked": result.candles_walked,
                    "is_ambiguous": result.is_ambiguous,
                    "notes": result.notes,
                },
                on_conflict="signal_id",
            ).execute()

            affected_channels.add(sig["channel_id"])

        except EntryNeverFilledError:
            # Entry never reached; leave as unresolved for now
            pass
        except MT5NotConnectedError as exc:
            logger.warning("MT5 not connected during verification pass: %s", exc)
            break   # no point continuing if MT5 is down
        except Exception as exc:
            logger.error("Unexpected error verifying signal %s: %s", sig["id"], exc)

    for channel_id in affected_channels:
        try:
            compute_trust_score(channel_id, db)
        except Exception as exc:
            logger.error("Score update failed for channel %s: %s", channel_id, exc)

    return len(rows)


# ─── Background scheduler ─────────────────────────────────────────────────────

async def _verification_loop() -> None:
    db = _make_db()
    while True:
        try:
            processed = await asyncio.to_thread(_run_verification_pass, db)
            if processed:
                logger.info("Verification pass: processed %d signals", processed)
        except Exception as exc:
            logger.error("Verification loop error: %s", exc)
        await asyncio.sleep(VERIFY_INTERVAL_SECS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_verification_loop())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(title="XAU Trust Score API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/channels")
async def get_channels() -> list[dict]:
    db = _make_db()
    rows = (
        db.table("channels")
        .select("*")
        .order("trust_score", desc=True)
        .execute()
        .data
    )
    return rows


@app.get("/channels/{channel_id}")
async def get_channel(channel_id: str) -> dict:
    db = _make_db()
    channel = (
        db.table("channels")
        .select("*")
        .eq("id", channel_id)
        .single()
        .execute()
        .data
    )
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    breakdown = (
        db.table("score_breakdowns")
        .select("*")
        .eq("channel_id", channel_id)
        .maybe_single()
        .execute()
        .data
    )

    return {"channel": channel, "score_breakdown": breakdown}


@app.get("/channels/{channel_id}/signals")
async def get_channel_signals(
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    db = _make_db()

    channel_check = (
        db.table("channels")
        .select("id")
        .eq("id", channel_id)
        .maybe_single()
        .execute()
        .data
    )
    if not channel_check:
        raise HTTPException(status_code=404, detail="Channel not found")

    signals = (
        db.table("signals")
        .select("*, signal_outcomes(*), messages(is_deleted)")
        .eq("channel_id", channel_id)
        .order("posted_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
        .data
    )

    # Attach edit history per signal
    for sig in signals:
        edits = (
            db.table("message_edits")
            .select("edit_number, content_before, content_after, edited_at, is_post_move_edit")
            .eq("message_id", sig["message_id"])
            .order("edit_number")
            .execute()
            .data
        )
        sig["edit_history"] = edits

    return signals


@app.post("/verify/run")
async def trigger_verification(background_tasks: BackgroundTasks) -> dict:
    """Manually trigger a verification pass (runs in background)."""
    db = _make_db()
    background_tasks.add_task(_run_verification_pass, db)
    return {"queued": True}
