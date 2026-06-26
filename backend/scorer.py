"""
Trust score calculator — Phase 3 implementation.

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
    score_to_verdict,
)


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

    Queries signal_outcomes, message_edits, screenshot_claims, and messages.
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
            .select("signal_id, outcome, points")
            .in_("signal_id", signal_ids)
            .neq("outcome", "unresolved")
            .execute()
            .data
        )

    # ── Q3: edit events ───────────────────────────────────────────────────────
    edit_rows = (
        db_client.table("message_edits")
        .select("is_post_move_edit")
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

    # ── Aggregate outcome stats ───────────────────────────────────────────────
    wins = losses = ambiguous = 0
    effective_wins = effective_total = 0.0
    weighted_points: list[tuple[float, float]] = []  # (points, weight)
    rr_values: list[float] = []
    backfill_count = live_count = 0

    for row in outcome_rows:
        sig = signal_map.get(row["signal_id"])
        if not sig:
            continue

        outcome = row["outcome"]
        weight = _signal_weight(sig.get("signal_type", "text"), sig.get("source", "live"))

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

    raw_performance = win_rate_component + rr_component + expectancy_component

    # ── Sample-size dampener ──────────────────────────────────────────────────
    ramp = MIN_SIGNALS_FULL_WEIGHT - MIN_SIGNALS_FLOOR
    sample_weight = _clamp((total_verified - MIN_SIGNALS_FLOOR) / ramp, 0.0, 1.0)
    adjusted_performance = raw_performance * sample_weight

    # ── Integrity component ───────────────────────────────────────────────────
    edit_count = len(edit_rows)
    post_move_edit_count = sum(1 for e in edit_rows if e.get("is_post_move_edit"))
    delete_signal_count = len(del_rows)
    contradicted_count = sum(1 for s in shot_rows if s.get("verdict") == "contradicted")

    integrity = WEIGHT_INTEGRITY
    integrity -= post_move_edit_count * PENALTY_POST_MOVE_EDIT
    integrity -= delete_signal_count * PENALTY_DELETED_SIGNAL
    integrity -= contradicted_count * PENALTY_CONTRADICTED_SCREENSHOT
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
        },
        on_conflict="channel_id",
    ).execute()

    db_client.table("channels").update(
        {"trust_score": int(breakdown.final_score), "verdict": verdict}
    ).eq("id", channel_id).execute()

    return breakdown
