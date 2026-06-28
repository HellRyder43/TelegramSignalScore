/**
 * Pure data-transformation functions that coerce raw Supabase rows into the
 * TypeScript types used by the UI.
 *
 * Supabase returns NUMERIC/DECIMAL columns as strings (to preserve precision)
 * and BIGINT as strings. We coerce everything to JS numbers here so the rest
 * of the app can treat them as numbers as the types promise.
 *
 * No server-only imports — this module is safe to import from client components.
 */

import type {
  Channel,
  ScoreBreakdown,
  Signal,
  SignalOutcome,
  MessageEdit,
  ScreenshotClaim,
  NonSignalMessage,
} from './types'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Row = Record<string, any>

const n = (v: unknown): number => Number(v ?? 0)
const ns = (v: unknown): number | null => (v == null ? null : Number(v))
const s = (v: unknown): string => String(v ?? '')

export function transformChannel(row: Row): Channel {
  return {
    id: s(row.id),
    telegram_id: n(row.telegram_id),
    name: s(row.name),
    username: row.username ? s(row.username) : null,
    member_count: ns(row.member_count),
    trust_score: n(row.trust_score),
    verdict: row.verdict as Channel['verdict'],
    verified_win_rate: ns(row.verified_win_rate),
    sample_size: n(row.sample_size),
    total_points: n(row.total_points),
    avg_risk_reward: ns(row.avg_risk_reward),
    edit_count: n(row.edit_count),
    delete_count: n(row.delete_count),
    screenshot_confirmed: n(row.screenshot_confirmed),
    screenshot_contradicted: n(row.screenshot_contradicted),
    last_signal_at: row.last_signal_at ? s(row.last_signal_at) : null,
    created_at: s(row.created_at),
  }
}

export function transformBreakdown(row: Row): ScoreBreakdown {
  return {
    channel_id: s(row.channel_id),
    win_rate_component: n(row.win_rate_component),
    rr_component: n(row.rr_component),
    expectancy_component: n(row.expectancy_component),
    raw_performance: n(row.raw_performance),
    sample_weight: n(row.sample_weight),
    adjusted_performance: n(row.adjusted_performance),
    integrity_score: n(row.integrity_score),
    final_score: n(row.final_score),
    details: {
      win_rate_pct: ns(row.win_rate_pct),
      total_verified: n(row.total_verified),
      wins: n(row.wins),
      losses: n(row.losses),
      ambiguous: n(row.ambiguous),
      avg_points_per_trade: ns(row.avg_points_per_trade),
      avg_risk_reward: ns(row.avg_risk_reward),
      edit_count: n(row.edit_count),
      post_move_edit_count: n(row.post_move_edit_count),
      delete_signal_count: n(row.delete_signal_count),
      contradicted_screenshot_count: n(row.contradicted_screenshot_count),
      backfill_signal_count: n(row.backfill_signal_count),
      live_signal_count: n(row.live_signal_count),
    },
  }
}

export function transformMessageEdit(row: Row): MessageEdit {
  return {
    id: s(row.id),
    message_id: s(row.message_id),
    channel_id: s(row.channel_id),
    edit_number: n(row.edit_number),
    content_before: s(row.content_before),
    content_after: s(row.content_after),
    edited_at: s(row.edited_at),
    is_post_move_edit: Boolean(row.is_post_move_edit),
  }
}

function transformOutcome(row: Row): SignalOutcome {
  return {
    id: s(row.id),
    signal_id: s(row.signal_id),
    outcome: row.outcome as SignalOutcome['outcome'],
    points: ns(row.points),
    candles_walked: row.candles_walked != null ? n(row.candles_walked) : null,
    verified_at: row.verified_at ? s(row.verified_at) : null,
    is_ambiguous: Boolean(row.is_ambiguous),
    notes: row.notes ? s(row.notes) : null,
  }
}

export function transformSignal(row: Row, editsMap: Map<string, MessageEdit[]>): Signal {
  // signal_outcomes is an array from the Supabase join; take the first (1:1 relation)
  const outcomeRows: Row[] = row.signal_outcomes ?? []
  const outcome: SignalOutcome | null =
    outcomeRows.length > 0 ? transformOutcome(outcomeRows[0]) : null

  const messageId = s(row.message_id)

  return {
    id: s(row.id),
    channel_id: s(row.channel_id),
    message_id: messageId,
    signal_type: row.signal_type as Signal['signal_type'],
    source: row.source as Signal['source'],
    direction: row.direction as Signal['direction'],
    entry: ns(row.entry),
    entry_low: ns(row.entry_low),
    entry_high: ns(row.entry_high),
    stop_loss: ns(row.stop_loss),
    take_profit_1: ns(row.take_profit_1),
    take_profit_2: ns(row.take_profit_2),
    take_profit_3: ns(row.take_profit_3),
    raw_text: s(row.raw_text),
    parsed_at: s(row.parsed_at),
    posted_at: s(row.posted_at),
    confidence: n(row.confidence),
    outcome,
    edits: editsMap.get(messageId) ?? [],
  }
}

export function transformScreenshot(row: Row): ScreenshotClaim {
  return {
    id: s(row.id),
    channel_id: s(row.channel_id),
    message_id: s(row.message_id),
    claimed_direction: row.claimed_direction
      ? (row.claimed_direction as ScreenshotClaim['claimed_direction'])
      : null,
    claimed_open: ns(row.claimed_open),
    claimed_close: ns(row.claimed_close),
    claimed_profit_pts: ns(row.claimed_profit_pts),
    claimed_open_time: row.claimed_open_time ? s(row.claimed_open_time) : null,
    claimed_close_time: row.claimed_close_time ? s(row.claimed_close_time) : null,
    verdict: row.verdict as ScreenshotClaim['verdict'],
    posted_at: s(row.posted_at),
    notes: row.notes ? s(row.notes) : null,
  }
}

export function transformNonSignal(row: Row): NonSignalMessage {
  return {
    id: s(row.id),
    channel_id: s(row.channel_id),
    message_id: s(row.id), // messages.id (UUID) — telegram_message_id not needed in UI
    message_type: row.message_type as NonSignalMessage['message_type'],
    content: row.content ? s(row.content) : null,
    posted_at: s(row.posted_at),
    is_deleted: Boolean(row.is_deleted),
    source: row.source as NonSignalMessage['source'],
  }
}

/** Default breakdown used when a channel has no score_breakdowns row yet. */
export function emptyBreakdown(channelId: string): ScoreBreakdown {
  return {
    channel_id: channelId,
    win_rate_component: 0,
    rr_component: 0,
    expectancy_component: 0,
    raw_performance: 0,
    sample_weight: 0,
    adjusted_performance: 0,
    integrity_score: 25,
    final_score: 0,
    details: {
      win_rate_pct: null,
      total_verified: 0,
      wins: 0,
      losses: 0,
      ambiguous: 0,
      avg_points_per_trade: null,
      avg_risk_reward: null,
      edit_count: 0,
      post_move_edit_count: 0,
      delete_signal_count: 0,
      contradicted_screenshot_count: 0,
      backfill_signal_count: 0,
      live_signal_count: 0,
    },
  }
}
