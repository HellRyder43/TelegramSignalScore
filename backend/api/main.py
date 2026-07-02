"""
FastAPI application — Phase 3 implementation.
"""

from __future__ import annotations
import asyncio
import logging
import sys
from contextlib import asynccontextmanager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    VERIFY_INTERVAL_SECS,
    MT5_SYMBOL,
    DISCORD_BOT_TOKEN,
    DISCORD_CHANNEL_ID,
    ANTHROPIC_API_KEY,
    AI_CHANNEL_ANALYSIS_ENABLED,
    AI_CHANNEL_ANALYSIS_MIN_SIGNALS,
    AI_CHANNEL_ANALYSIS_MIN_INTERVAL_SECS,
    SYNTHETIC_EXIT_ENABLED,
)
from backend.verifier import (
    verify_signal,
    verify_signal_synthetic,
    MT5NotConnectedError,
    EntryNeverFilledError,
)
from backend.scorer import compute_trust_score
from backend.notifier.base import Notifier
from backend.db_utils import maybe_one

logger = logging.getLogger(__name__)

# ─── Supabase client ──────────────────────────────────────────────────────────

def _make_db() -> Client:
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ─── AI channel analysis helpers ─────────────────────────────────────────────

def _build_channel_summary(db: Client, channel_id: str, channel_row: dict) -> dict:
    """Build the summary_data dict expected by analyze_channel_behavior()."""
    # Total resolved signals and win rate
    sig_rows = (
        db.table("signals")
        .select("id, source")
        .eq("channel_id", channel_id)
        .execute()
        .data
    )
    signal_ids = [r["id"] for r in sig_rows]

    outcome_rows: list[dict] = []
    if signal_ids:
        outcome_rows = (
            db.table("signal_outcomes")
            .select("signal_id, outcome, candles_walked")
            .in_("signal_id", signal_ids)
            .neq("outcome", "unresolved")
            .execute()
            .data
        )

    total_signals = len(outcome_rows)
    wins = sum(1 for r in outcome_rows if r.get("outcome") == "win")
    win_rate_pct = (wins / total_signals * 100) if total_signals else 0.0

    # Timing: avg candles from post → entry fill (lower = earlier = less suspicious)
    candles = [r["candles_walked"] for r in outcome_rows if r.get("candles_walked") is not None]
    avg_candles = sum(candles) / len(candles) if candles else None
    timing_summary = (
        f"Avg {avg_candles:.1f} M1 candles from post to entry fill across {len(candles)} signals."
        if avg_candles is not None
        else "No timing data available."
    )

    # Quality flags
    retro_count = low_q_count = 0
    if signal_ids:
        qa_rows = (
            db.table("signal_quality_assessments")
            .select("signal_id, quality_score, is_retrospective")
            .in_("signal_id", signal_ids)
            .execute()
            .data
        )
        retro_count = sum(1 for r in qa_rows if r.get("is_retrospective"))
        from backend.config import AI_LOW_QUALITY_THRESHOLD
        low_q_count = sum(
            1 for r in qa_rows
            if not r.get("is_retrospective") and float(r.get("quality_score") or 1) < AI_LOW_QUALITY_THRESHOLD
        )

    # Edit pattern
    edit_rows = (
        db.table("message_edits")
        .select("is_post_move_edit, ai_intent, ai_suspicion_score")
        .eq("channel_id", channel_id)
        .execute()
        .data
    )
    post_move = sum(1 for e in edit_rows if e.get("is_post_move_edit"))
    suspicious = sum(1 for e in edit_rows if (e.get("ai_suspicion_score") or 0) >= 0.5)
    intent_counts: dict[str, int] = {}
    for e in edit_rows:
        intent = e.get("ai_intent") or "unknown"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    edit_summary = (
        f"{len(edit_rows)} edits total; {post_move} post-move; {suspicious} suspicious. "
        f"Intents: {intent_counts}."
    ) if edit_rows else "No edits recorded."

    # Delete pattern
    msg_rows = (
        db.table("messages")
        .select("id, is_deleted")
        .eq("channel_id", channel_id)
        .eq("message_type", "text_signal")
        .execute()
        .data
    )
    deleted_ids = {r["id"] for r in msg_rows if r.get("is_deleted")}
    deleted_count = len(deleted_ids)
    delete_summary = (
        f"{deleted_count} signal(s) deleted out of {len(msg_rows)} text signals."
        if msg_rows
        else "No signal messages found."
    )

    return {
        "total_signals": total_signals,
        "win_rate_pct": win_rate_pct,
        "retrospective_count": retro_count,
        "low_quality_count": low_q_count,
        "edit_summary": edit_summary,
        "delete_summary": delete_summary,
        "timing_summary": timing_summary,
        "screenshot_confirmed": channel_row.get("screenshot_confirmed", 0),
        "screenshot_contradicted": channel_row.get("screenshot_contradicted", 0),
    }


def _run_channel_analysis_for(db: Client, channel_ids: set[str], force: bool = False) -> int:
    """
    Run AI channel behavior analysis for the given channel UUIDs.
    Skips if AI is disabled or API key missing.
    Returns count of channels actually analyzed.

    Each run costs a Claude call. The automatic verification loop calls this with
    force=False, so a channel assessed within AI_CHANNEL_ANALYSIS_MIN_INTERVAL_SECS
    is skipped — otherwise every 5-minute pass that resolves a signal would re-bill
    Claude for the same channel. Manual triggers pass force=True to override.
    """
    if not (AI_CHANNEL_ANALYSIS_ENABLED and ANTHROPIC_API_KEY):
        return 0

    from backend.ai.channel_analyzer import analyze_channel_behavior
    from datetime import datetime, timezone

    analyzed = 0
    for channel_id in channel_ids:
        try:
            channel_row = maybe_one(
                db.table("channels")
                .select("*")
                .eq("id", channel_id)
            )
            if not channel_row:
                continue

            # Cost guard: skip channels assessed very recently unless forced.
            if not force:
                prior = maybe_one(
                    db.table("channel_ai_assessments")
                    .select("assessed_at")
                    .eq("channel_id", channel_id)
                )
                if prior and prior.get("assessed_at"):
                    last = datetime.fromisoformat(prior["assessed_at"].replace("Z", "+00:00"))
                    if last.tzinfo is None:
                        last = last.replace(tzinfo=timezone.utc)
                    age = (datetime.now(timezone.utc) - last).total_seconds()
                    if age < AI_CHANNEL_ANALYSIS_MIN_INTERVAL_SECS:
                        continue

            summary = _build_channel_summary(db, channel_id, channel_row)
            if summary["total_signals"] < AI_CHANNEL_ANALYSIS_MIN_SIGNALS:
                continue

            result = analyze_channel_behavior(channel_row.get("name", channel_id), summary)
            if result is None:
                continue

            db.table("channel_ai_assessments").upsert(
                {
                    "channel_id": channel_id,
                    "fraud_risk_score": result.fraud_risk_score,
                    "timing_score": result.timing_score,
                    "edit_manipulation_score": result.edit_manipulation_score,
                    "delete_manipulation_score": result.delete_manipulation_score,
                    "key_findings": result.key_findings,
                    "signals_analyzed": result.signals_analyzed,
                    "assessed_at": datetime.now(timezone.utc).isoformat(),
                },
                on_conflict="channel_id",
            ).execute()

            analyzed += 1
        except Exception as exc:
            logger.warning("Channel analysis failed for %s (non-fatal): %s", channel_id, exc)

    return analyzed


# ─── Verification pass ────────────────────────────────────────────────────────

ResolutionAlert = tuple[str, str, float | None]  # (discord_msg_id, outcome, points)


def _run_verification_pass(db: Client) -> tuple[int, list[ResolutionAlert]]:
    """
    Resolve all unresolved signals.
    Returns (signals_processed, resolution_alerts).
    resolution_alerts is a list of (discord_message_id, outcome, points) for
    signals that resolved and have a Discord alert — caller sends the follow-ups.
    """
    rows = (
        db.table("signals")
        .select("id, channel_id, direction, entry, stop_loss, take_profit_1, posted_at")
        .eq("resolution_status", "unresolved")
        .execute()
        .data
    )

    if not rows:
        return 0, []

    affected_channels: set[str] = set()
    resolution_alerts: list[ResolutionAlert] = []
    skipped = 0

    for sig in rows:
        # Verification needs a concrete entry price. Without one there is nothing
        # to fill against, so skip (crash-safe vs float(None)); stays unresolved.
        if sig.get("entry") is None:
            skipped += 1
            continue
        try:
            if sig.get("stop_loss") is None:
                # No stated stop-loss → symmetric synthetic time-horizon exit.
                # (A first-touch check with only a TP could ever record a win,
                # which would bias the record; the time-exit can go either way.)
                if not SYNTHETIC_EXIT_ENABLED:
                    skipped += 1
                    continue
                result = verify_signal_synthetic(
                    direction=sig["direction"],
                    entry=float(sig["entry"]),
                    posted_at=sig["posted_at"],
                    symbol=MT5_SYMBOL,
                )
            else:
                tp1 = sig.get("take_profit_1")
                result = verify_signal(
                    direction=sig["direction"],
                    entry=float(sig["entry"]),
                    stop_loss=float(sig["stop_loss"]),
                    # None lets verify_signal apply its default-TP fallback.
                    take_profit=float(tp1) if tp1 is not None else None,
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
                    "method": result.method,
                },
                on_conflict="signal_id",
            ).execute()

            affected_channels.add(sig["channel_id"])

            # Collect Discord alert ID for resolution follow-up
            alert_rows = (
                db.table("discord_alerts")
                .select("discord_message_id")
                .eq("signal_id", sig["id"])
                .eq("alert_type", "signal")
                .limit(1)
                .execute()
                .data
            )
            if alert_rows:
                resolution_alerts.append((
                    alert_rows[0]["discord_message_id"],
                    result.outcome,
                    result.points,
                ))

        except EntryNeverFilledError:
            pass
        except MT5NotConnectedError as exc:
            logger.warning("MT5 not connected during verification pass: %s", exc)
            break
        except Exception as exc:
            logger.error("Unexpected error verifying signal %s: %s", sig["id"], exc)

    for channel_id in affected_channels:
        try:
            compute_trust_score(channel_id, db)
        except Exception as exc:
            logger.error("Score update failed for channel %s: %s", channel_id, exc)

    if affected_channels:
        try:
            _run_channel_analysis_for(db, affected_channels)
        except Exception as exc:
            logger.error("Channel AI analysis failed (non-fatal): %s", exc)

    if skipped:
        logger.info(
            "Verification pass: skipped %d signal(s) missing entry/stop-loss (unverifiable)",
            skipped,
        )

    return len(rows) - skipped, resolution_alerts


# ─── Background scheduler ─────────────────────────────────────────────────────

async def _verification_loop(notifier: Notifier | None) -> None:
    db = _make_db()
    while True:
        try:
            processed, resolution_alerts = await asyncio.to_thread(_run_verification_pass, db)
            if processed:
                logger.info("Verification pass: processed %d signals", processed)
            if notifier and resolution_alerts:
                for discord_msg_id, outcome, points in resolution_alerts:
                    try:
                        await notifier.send_resolution_followup(discord_msg_id, outcome, points)
                    except Exception as exc:
                        logger.warning("Resolution follow-up failed (non-fatal): %s", exc)
        except Exception as exc:
            logger.error("Verification loop error: %s", exc)
        await asyncio.sleep(VERIFY_INTERVAL_SECS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    notifier: Notifier | None = None
    if DISCORD_BOT_TOKEN and DISCORD_CHANNEL_ID:
        from backend.notifier.discord_bot import DiscordNotifier
        notifier = DiscordNotifier(_make_db())
        logger.info("Discord notifier initialized")
    else:
        logger.info("DISCORD_BOT_TOKEN / DISCORD_CHANNEL_ID not set — resolution alerts disabled")

    task = asyncio.create_task(_verification_loop(notifier))
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    if notifier:
        await notifier.close()


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

    breakdown = maybe_one(
        db.table("score_breakdowns")
        .select("*")
        .eq("channel_id", channel_id)
    )

    return {"channel": channel, "score_breakdown": breakdown}


@app.get("/channels/{channel_id}/signals")
async def get_channel_signals(
    channel_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    db = _make_db()

    channel_check = maybe_one(
        db.table("channels")
        .select("id")
        .eq("id", channel_id)
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


@app.post("/ai/assess/channel/{channel_id}")
async def trigger_channel_assessment(channel_id: str) -> dict:
    """Manually trigger AI behavior analysis for a single channel."""
    db = _make_db()
    # force=True: a manual trigger should always produce a fresh assessment,
    # bypassing the automatic-loop recency guard.
    count = await asyncio.to_thread(_run_channel_analysis_for, db, {channel_id}, True)
    return {"analyzed": count}
