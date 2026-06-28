"""
AI retroactive assessment CLI — Phase 8.

Run AI assessments against existing database rows that were created
before Phase 8 was deployed (or to re-run after config changes).

Usage (from project root with venv active):
    python -m scripts.ai_assess --mode signals --limit 100
    python -m scripts.ai_assess --mode edits   --limit 100
    python -m scripts.ai_assess --mode channels
    python -m scripts.ai_assess --mode all

Options:
    --mode      {signals, edits, channels, all}  (required)
    --channel   filter by channel name substring  (optional)
    --limit     max rows per mode, default 500
    --delay     seconds between Claude calls, default 1.0
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ai_assess")

from backend.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    ANTHROPIC_API_KEY,
    AI_CHANNEL_ANALYSIS_MIN_SIGNALS,
    AI_LOW_QUALITY_THRESHOLD,
)
from supabase import create_client


def _make_db():
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ─── signals mode ─────────────────────────────────────────────────────────────

def run_signals(db, channel_filter: str | None, limit: int, delay: float) -> int:
    from backend.ai.quality_assessor import assess_signal_quality

    # Fetch signals not yet assessed
    q = (
        db.table("signals")
        .select("id, raw_text, channel_id")
        .limit(limit)
    )
    sig_rows = q.execute().data

    # Filter out already-assessed
    if sig_rows:
        assessed_ids = {
            r["signal_id"] for r in (
                db.table("signal_quality_assessments")
                .select("signal_id")
                .in_("signal_id", [r["id"] for r in sig_rows])
                .execute()
                .data
            )
        }
        sig_rows = [r for r in sig_rows if r["id"] not in assessed_ids]

    if channel_filter:
        channel_ids = {
            r["id"] for r in (
                db.table("channels")
                .select("id, name")
                .ilike("name", f"%{channel_filter}%")
                .execute()
                .data
            )
        }
        sig_rows = [r for r in sig_rows if r.get("channel_id") in channel_ids]

    logger.info("Assessing quality for %d signals...", len(sig_rows))
    done = 0

    for i, row in enumerate(sig_rows):
        raw_text = row.get("raw_text") or ""
        if not raw_text.strip():
            continue
        try:
            qa = assess_signal_quality(raw_text)
            if qa:
                db.table("signal_quality_assessments").upsert(
                    {
                        "signal_id": row["id"],
                        "quality_score": qa.quality_score,
                        "is_retrospective": qa.is_retrospective,
                        "flags": qa.flags,
                        "explanation": qa.explanation,
                    },
                    on_conflict="signal_id",
                ).execute()
                done += 1
            if (i + 1) % 10 == 0:
                logger.info("  %d / %d done", i + 1, len(sig_rows))
        except Exception as exc:
            logger.warning("Failed on signal %s: %s", row["id"], exc)
        time.sleep(delay)

    logger.info("Signals: assessed %d rows.", done)
    return done


# ─── edits mode ───────────────────────────────────────────────────────────────

def run_edits(db, channel_filter: str | None, limit: int, delay: float) -> int:
    from backend.ai.edit_analyzer import analyze_edit_intent

    q = (
        db.table("message_edits")
        .select("message_id, edit_number, content_before, content_after, is_post_move_edit, channel_id")
        .is_("ai_intent", "null")
        .limit(limit)
    )
    rows = q.execute().data

    if channel_filter:
        channel_ids = {
            r["id"] for r in (
                db.table("channels")
                .select("id, name")
                .ilike("name", f"%{channel_filter}%")
                .execute()
                .data
            )
        }
        rows = [r for r in rows if r.get("channel_id") in channel_ids]

    logger.info("Analyzing intent for %d edits...", len(rows))
    done = 0

    for i, row in enumerate(rows):
        try:
            analysis = analyze_edit_intent(
                row.get("content_before") or "",
                row.get("content_after") or "",
                bool(row.get("is_post_move_edit")),
            )
            if analysis:
                db.table("message_edits").update(
                    {
                        "ai_intent": analysis.intent,
                        "ai_suspicion_score": analysis.suspicion_score,
                        "ai_intent_notes": analysis.notes,
                        "ai_assessed_at": datetime.now(timezone.utc).isoformat(),
                    }
                ).eq("message_id", row["message_id"]).eq("edit_number", row["edit_number"]).execute()
                done += 1
            if (i + 1) % 10 == 0:
                logger.info("  %d / %d done", i + 1, len(rows))
        except Exception as exc:
            logger.warning("Failed on edit %s/%s: %s", row["message_id"], row["edit_number"], exc)
        time.sleep(delay)

    logger.info("Edits: analyzed %d rows.", done)
    return done


# ─── channels mode ────────────────────────────────────────────────────────────

def _build_channel_summary(db, channel_id: str, channel_row: dict) -> dict:
    """Duplicate of api/main.py helper to avoid circular imports."""
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

    candles = [r["candles_walked"] for r in outcome_rows if r.get("candles_walked") is not None]
    avg_candles = sum(candles) / len(candles) if candles else None
    timing_summary = (
        f"Avg {avg_candles:.1f} M1 candles from post to entry fill across {len(candles)} signals."
        if avg_candles is not None
        else "No timing data available."
    )

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
        low_q_count = sum(
            1 for r in qa_rows
            if not r.get("is_retrospective") and float(r.get("quality_score") or 1) < AI_LOW_QUALITY_THRESHOLD
        )

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
        f"{len(edit_rows)} edits total; {post_move} post-move; {suspicious} suspicious. Intents: {intent_counts}."
        if edit_rows else "No edits recorded."
    )

    msg_rows = (
        db.table("messages")
        .select("id, is_deleted")
        .eq("channel_id", channel_id)
        .eq("message_type", "text_signal")
        .execute()
        .data
    )
    deleted_count = sum(1 for r in msg_rows if r.get("is_deleted"))
    delete_summary = (
        f"{deleted_count} signal(s) deleted out of {len(msg_rows)} text signals."
        if msg_rows else "No signal messages found."
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


def run_channels(db, channel_filter: str | None, delay: float) -> int:
    from backend.ai.channel_analyzer import analyze_channel_behavior
    from backend.scorer import compute_trust_score

    q = db.table("channels").select("*")
    if channel_filter:
        q = q.ilike("name", f"%{channel_filter}%")
    channel_rows = q.execute().data

    logger.info("Analyzing behavior for %d channels...", len(channel_rows))
    done = 0

    for channel_row in channel_rows:
        channel_id = channel_row["id"]
        try:
            summary = _build_channel_summary(db, channel_id, channel_row)
            if summary["total_signals"] < AI_CHANNEL_ANALYSIS_MIN_SIGNALS:
                logger.info(
                    "  Skipping %s — only %d resolved signals (need %d)",
                    channel_row.get("name"), summary["total_signals"], AI_CHANNEL_ANALYSIS_MIN_SIGNALS,
                )
                continue

            result = analyze_channel_behavior(channel_row.get("name", channel_id), summary)
            if result is None:
                logger.warning("  No result for channel %s", channel_row.get("name"))
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

            # Immediately recompute trust score so penalty is reflected
            compute_trust_score(channel_id, db)
            done += 1
            logger.info(
                "  %s — fraud_risk=%.2f, findings: %s",
                channel_row.get("name"),
                result.fraud_risk_score,
                result.key_findings[:120],
            )
        except Exception as exc:
            logger.warning("Failed on channel %s: %s", channel_row.get("name"), exc)
        time.sleep(delay)

    logger.info("Channels: analyzed %d.", done)
    return done


# ─── CLI entry ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Retroactive AI assessments")
    parser.add_argument("--mode", required=True, choices=["signals", "edits", "channels", "all"])
    parser.add_argument("--channel", default=None, help="Filter by channel name substring")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--delay", type=float, default=1.0)
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        logger.error("ANTHROPIC_API_KEY not set in .env — aborting.")
        sys.exit(1)

    db = _make_db()

    if args.mode in ("signals", "all"):
        run_signals(db, args.channel, args.limit, args.delay)
    if args.mode in ("edits", "all"):
        run_edits(db, args.channel, args.limit, args.delay)
    if args.mode in ("channels", "all"):
        run_channels(db, args.channel, args.delay)


if __name__ == "__main__":
    main()
