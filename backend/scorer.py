"""
Trust score calculator — Phase 3 + Phase 8 (AI intelligence).

Aggregates verified outcomes and integrity events into a per-channel
Trust Score (0–100) with a fully explainable breakdown.
"""

from __future__ import annotations
from dataclasses import dataclass

from backend.config import (
    WEIGHT_WIN_RATE,
    WEIGHT_RR,
    WEIGHT_EXPECTANCY,
    WEIGHT_INTEGRITY,
    MIN_SIGNALS_FULL_WEIGHT,
    MIN_SIGNALS_FLOOR,
    PENALTY_POST_MOVE_EDIT,
    PENALTY_DELETED_SIGNAL,
    PENALTY_CONTRADICTED_SCREENSHOT,
    BACKFILL_SIGNAL_WEIGHT,
    ZONE_SIGNAL_WEIGHT,
    SYNTHETIC_SIGNAL_WEIGHT,
    score_to_verdict,
    AI_LOW_QUALITY_THRESHOLD,
    AI_LOW_QUALITY_WEIGHT,
    PENALTY_AI_SUSPICIOUS_EDIT,
    AI_BEHAVIOR_PENALTY_MAX,
)
from backend.db_utils import maybe_one


@dataclass
class ScoreBreakdown:
    channel_id: str

    win_rate_component: float      # 0–40
    rr_component: float            # 0–25
    expectancy_component: float    # 0–20
    raw_performance: float         # sum of above three

    sample_weight: float           # 0.0–1.0 dampener
    adjusted_performance: float    # raw_performance × sample_weight

    integrity_score: float         # 0–25 (penalties reduce from max)
    final_score: float             # adjusted_performance + integrity_score

    # Detail snapshot used in dashboard breakdown panel
    win_rate_pct: float | None
    total_verified: int
    wins: int
    losses: int
    ambiguous: int
    avg_points_per_trade: float | None
    avg_risk_reward: float | None
    edit_count: int
    post_move_edit_count: int
    delete_signal_count: int
    contradicted_screenshot_count: int
    backfill_signal_count: int
    live_signal_count: int

    # Phase 8 AI fields
    retrospective_signal_count: int
    low_quality_signal_count: int
    suspicious_edit_count: int
    ai_behavior_penalty: float
    quality_weight_adjustment: float


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _signal_weight(signal_type: str, source: str) -> float:
    w = 1.0
    if source == "backfill":
        w *= BACKFILL_SIGNAL_WEIGHT
    if signal_type == "zone_estimated":
        w *= ZONE_SIGNAL_WEIGHT
    return w


def compute_trust_score(channel_id: str, db_client) -> ScoreBreakdown:
    """
    Compute the Trust Score for a channel from its Supabase data.

    Queries signal_outcomes, message_edits, screenshot_claims, messages,
    signal_quality_assessments, and channel_ai_assessments.
    Returns a ScoreBreakdown with every component exposed for the dashboard.
    After computing, upserts score_breakdowns and updates channels.trust_score.
    """
    # ── Q1: signals for this channel ──────────────────────────────────────────
    sig_rows = (
        db_client.table("signals")
        .select("id, signal_type, source, entry, stop_loss, take_profit_1, direction, message_id")
        .eq("channel_id", channel_id)
        .execute()
        .data
    )

    signal_map = {s["id"]: s for s in sig_rows}
    signal_ids = list(signal_map.keys())
    msg_ids = [s["message_id"] for s in sig_rows if s.get("message_id")]

    # ── Q2: resolved outcomes ─────────────────────────────────────────────────
    outcome_rows: list[dict] = []
    if signal_ids:
        outcome_rows = (
            db_client.table("signal_outcomes")
            .select("signal_id, outcome, points, method")
            .in_("signal_id", signal_ids)
            .neq("outcome", "unresolved")
            .execute()
            .data
        )

    # ── Q3: edit events (with AI columns) ────────────────────────────────────
    edit_rows = (
        db_client.table("message_edits")
        .select("is_post_move_edit, ai_intent, ai_suspicion_score")
        .eq("channel_id", channel_id)
        .execute()
        .data
    )

    # ── Q4: screenshot verdicts ───────────────────────────────────────────────
    shot_rows = (
        db_client.table("screenshot_claims")
        .select("verdict")
        .eq("channel_id", channel_id)
        .execute()
        .data
    )

    # ── Q5: deleted signal messages ───────────────────────────────────────────
    del_rows: list[dict] = []
    if msg_ids:
        del_rows = (
            db_client.table("messages")
            .select("id")
            .in_("id", msg_ids)
            .eq("is_deleted", True)
            .execute()
            .data
        )

    # ── Q6: AI quality assessments ────────────────────────────────────────────
    quality_map: dict[str, dict] = {}
    if signal_ids:
        qa_rows = (
            db_client.table("signal_quality_assessments")
            .select("signal_id, quality_score, is_retrospective")
            .in_("signal_id", signal_ids)
            .execute()
            .data
        )
        quality_map = {r["signal_id"]: r for r in qa_rows}

    # ── Q7: channel AI behavior assessment ───────────────────────────────────
    ai_assessment_row: dict | None = maybe_one(
        db_client.table("channel_ai_assessments")
        .select("fraud_risk_score")
        .eq("channel_id", channel_id)
    )

    # ── Aggregate outcome stats ───────────────────────────────────────────────
    wins = losses = ambiguous = 0
    effective_wins = effective_total = 0.0
    weighted_points: list[tuple[float, float]] = []  # (points, weight)
    rr_values: list[float] = []
    backfill_count = live_count = 0
    retrospective_count = 0
    low_quality_count = 0
    quality_weight_adjustment_total = 0.0

    for row in outcome_rows:
        sig = signal_map.get(row["signal_id"])
        if not sig:
            continue

        # Exclude retrospective signals from all stats
        qa = quality_map.get(row["signal_id"])
        if qa and qa.get("is_retrospective"):
            retrospective_count += 1
            continue

        outcome = row["outcome"]
        weight = _signal_weight(sig.get("signal_type", "text"), sig.get("source", "live"))

        # Estimated (no stated stop-loss) outcomes count for less.
        if row.get("method") == "synthetic_horizon":
            weight *= SYNTHETIC_SIGNAL_WEIGHT

        # Downweight low-quality signals
        if qa:
            qs = float(qa.get("quality_score") or 1.0)
            if qs < AI_LOW_QUALITY_THRESHOLD:
                quality_weight_adjustment_total += weight * (1.0 - AI_LOW_QUALITY_WEIGHT)
                weight *= AI_LOW_QUALITY_WEIGHT
                low_quality_count += 1

        if sig.get("source") == "backfill":
            backfill_count += 1
        else:
            live_count += 1

        if outcome == "win":
            wins += 1
            effective_wins += weight
            effective_total += weight
        elif outcome == "loss":
            losses += 1
            effective_total += weight
        elif outcome == "ambiguous_loss":
            ambiguous += 1
            effective_total += weight

        if row.get("points") is not None:
            weighted_points.append((row["points"], weight))

        # R:R for this signal
        entry = sig.get("entry")
        sl = sig.get("stop_loss")
        tp = sig.get("take_profit_1")
        if entry and sl and tp and abs(entry - sl) > 0:
            rr = abs(tp - entry) / abs(entry - sl)
            rr_values.append(rr)

    total_verified = wins + losses + ambiguous

    # ── Performance components ────────────────────────────────────────────────
    if effective_total > 0:
        win_rate = effective_wins / effective_total
        win_rate_pct: float | None = win_rate * 100
    else:
        win_rate = 0.0
        win_rate_pct = None

    win_rate_component = win_rate * WEIGHT_WIN_RATE

    if rr_values:
        avg_rr: float | None = sum(rr_values) / len(rr_values)
        rr_component = _clamp(avg_rr / 3.0, 0.0, 1.0) * WEIGHT_RR
    else:
        avg_rr = None
        rr_component = 0.0

    if weighted_points:
        total_w = sum(w for _, w in weighted_points)
        avg_pts: float | None = sum(p * w for p, w in weighted_points) / total_w if total_w else 0.0
        expectancy_component = _clamp(avg_pts / 100.0, 0.0, 1.0) * WEIGHT_EXPECTANCY
    else:
        avg_pts = None
        expectancy_component = 0.0

    # Raw (unweighted) total points across verified signals — for the dashboard.
    total_points_raw = sum(p for p, _ in weighted_points) if weighted_points else 0.0

    raw_performance = win_rate_component + rr_component + expectancy_component

    # ── Sample-size dampener ──────────────────────────────────────────────────
    ramp = MIN_SIGNALS_FULL_WEIGHT - MIN_SIGNALS_FLOOR
    sample_weight = _clamp((total_verified - MIN_SIGNALS_FLOOR) / ramp, 0.0, 1.0)
    adjusted_performance = raw_performance * sample_weight

    # ── Integrity component (AI-aware) ────────────────────────────────────────
    edit_count = len(edit_rows)
    post_move_edit_count = sum(1 for e in edit_rows if e.get("is_post_move_edit"))
    delete_signal_count = len(del_rows)
    contradicted_count = sum(1 for s in shot_rows if s.get("verdict") == "contradicted")
    confirmed_count = sum(1 for s in shot_rows if s.get("verdict") == "confirmed")

    integrity = float(WEIGHT_INTEGRITY)
    total_edit_penalty = 0.0
    suspicious_edit_count_val = 0

    for e in edit_rows:
        ai_score = e.get("ai_suspicion_score")
        if ai_score is not None:
            # Continuous penalty: 0.0 for typos, up to 5.0 for clear manipulation
            per_edit = float(ai_score) * PENALTY_AI_SUSPICIOUS_EDIT
            if float(ai_score) >= 0.5:
                suspicious_edit_count_val += 1
        elif e.get("is_post_move_edit"):
            # Legacy fallback when AI analysis hasn't run for this edit
            per_edit = PENALTY_POST_MOVE_EDIT
            suspicious_edit_count_val += 1
        else:
            per_edit = 0.0
        total_edit_penalty += per_edit

    integrity -= total_edit_penalty
    integrity -= delete_signal_count * PENALTY_DELETED_SIGNAL
    integrity -= contradicted_count * PENALTY_CONTRADICTED_SCREENSHOT

    # Channel-level AI fraud penalty
    ai_behavior_penalty_val = 0.0
    if ai_assessment_row:
        fraud = float(ai_assessment_row.get("fraud_risk_score") or 0)
        ai_behavior_penalty_val = _clamp(fraud * AI_BEHAVIOR_PENALTY_MAX, 0, AI_BEHAVIOR_PENALTY_MAX)
        integrity -= ai_behavior_penalty_val

    integrity_score = max(0.0, integrity)

    # ── Final score ───────────────────────────────────────────────────────────
    final_score = float(int(_clamp(adjusted_performance + integrity_score, 0.0, 100.0)))

    breakdown = ScoreBreakdown(
        channel_id=channel_id,
        win_rate_component=round(win_rate_component, 2),
        rr_component=round(rr_component, 2),
        expectancy_component=round(expectancy_component, 2),
        raw_performance=round(raw_performance, 2),
        sample_weight=round(sample_weight, 4),
        adjusted_performance=round(adjusted_performance, 2),
        integrity_score=round(integrity_score, 2),
        final_score=final_score,
        win_rate_pct=round(win_rate_pct, 1) if win_rate_pct is not None else None,
        total_verified=total_verified,
        wins=wins,
        losses=losses,
        ambiguous=ambiguous,
        avg_points_per_trade=round(avg_pts, 1) if avg_pts is not None else None,
        avg_risk_reward=round(avg_rr, 2) if avg_rr is not None else None,
        edit_count=edit_count,
        post_move_edit_count=post_move_edit_count,
        delete_signal_count=delete_signal_count,
        contradicted_screenshot_count=contradicted_count,
        backfill_signal_count=backfill_count,
        live_signal_count=live_count,
        retrospective_signal_count=retrospective_count,
        low_quality_signal_count=low_quality_count,
        suspicious_edit_count=suspicious_edit_count_val,
        ai_behavior_penalty=round(ai_behavior_penalty_val, 2),
        quality_weight_adjustment=round(quality_weight_adjustment_total, 2),
    )

    # ── Persist to Supabase ───────────────────────────────────────────────────
    verdict = score_to_verdict(int(final_score))

    db_client.table("score_breakdowns").upsert(
        {
            "channel_id": channel_id,
            "win_rate_component": breakdown.win_rate_component,
            "rr_component": breakdown.rr_component,
            "expectancy_component": breakdown.expectancy_component,
            "raw_performance": breakdown.raw_performance,
            "sample_weight": breakdown.sample_weight,
            "adjusted_performance": breakdown.adjusted_performance,
            "integrity_score": breakdown.integrity_score,
            "final_score": int(breakdown.final_score),
            "win_rate_pct": breakdown.win_rate_pct,
            "total_verified": breakdown.total_verified,
            "wins": breakdown.wins,
            "losses": breakdown.losses,
            "ambiguous": breakdown.ambiguous,
            "avg_points_per_trade": breakdown.avg_points_per_trade,
            "avg_risk_reward": breakdown.avg_risk_reward,
            "edit_count": breakdown.edit_count,
            "post_move_edit_count": breakdown.post_move_edit_count,
            "delete_signal_count": breakdown.delete_signal_count,
            "contradicted_screenshot_count": breakdown.contradicted_screenshot_count,
            "backfill_signal_count": breakdown.backfill_signal_count,
            "live_signal_count": breakdown.live_signal_count,
            "retrospective_signal_count": breakdown.retrospective_signal_count,
            "low_quality_signal_count": breakdown.low_quality_signal_count,
            "suspicious_edit_count": breakdown.suspicious_edit_count,
            "ai_behavior_penalty": breakdown.ai_behavior_penalty,
            "quality_weight_adjustment": breakdown.quality_weight_adjustment,
        },
        on_conflict="channel_id",
    ).execute()

    db_client.table("channels").update(
        {
            "trust_score": int(breakdown.final_score),
            "verdict": verdict,
            # Denormalized display stats read directly by the overview dashboard.
            # All derived from source tables above, so this is idempotent.
            "verified_win_rate": (round(win_rate, 4) if win_rate_pct is not None else None),
            "sample_size": total_verified,
            "total_points": round(total_points_raw, 1),
            "avg_risk_reward": (round(avg_rr, 2) if avg_rr is not None else None),
            "edit_count": edit_count,
            "delete_count": delete_signal_count,
            "screenshot_confirmed": confirmed_count,
            "screenshot_contradicted": contradicted_count,
        }
    ).eq("id", channel_id).execute()

    return breakdown
