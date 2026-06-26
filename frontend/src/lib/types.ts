export type Verdict = 'avoid' | 'observe' | 'caution' | 'trusted'
export type SignalType = 'text' | 'zone_estimated'
export type SignalDirection = 'BUY' | 'SELL'
export type SignalSource = 'live' | 'backfill'
export type OutcomeType = 'win' | 'loss' | 'ambiguous_loss' | 'unresolved'
export type ScreenshotVerdict = 'confirmed' | 'contradicted' | 'unverifiable'

export interface Channel {
  id: string
  telegram_id: number
  name: string
  username: string | null
  member_count: number | null
  trust_score: number
  verdict: Verdict
  verified_win_rate: number | null  // 0–1 decimal
  sample_size: number               // count of verified signals
  total_points: number
  avg_risk_reward: number | null
  edit_count: number
  delete_count: number
  screenshot_confirmed: number
  screenshot_contradicted: number
  last_signal_at: string | null
  created_at: string
}

export interface ScoreBreakdown {
  channel_id: string
  win_rate_component: number      // 0–40
  rr_component: number            // 0–25
  expectancy_component: number    // 0–20
  raw_performance: number         // win_rate + rr + expectancy
  sample_weight: number           // 0.0–1.0 multiplier
  adjusted_performance: number    // raw_performance × sample_weight
  integrity_score: number         // 0–25 (penalties reduce from 25)
  final_score: number             // adjusted_performance + integrity_score
  details: {
    win_rate_pct: number | null
    total_verified: number
    wins: number
    losses: number
    ambiguous: number
    avg_points_per_trade: number | null
    avg_risk_reward: number | null
    edit_count: number
    post_move_edit_count: number
    delete_signal_count: number
    contradicted_screenshot_count: number
    backfill_signal_count: number
    live_signal_count: number
  }
}

export interface MessageEdit {
  id: string
  message_id: number
  channel_id: string
  edit_number: number
  content_before: string
  content_after: string
  edited_at: string
  is_post_move_edit: boolean
}

export interface SignalOutcome {
  id: string
  signal_id: string
  outcome: OutcomeType
  points: number | null
  candles_walked: number | null
  verified_at: string | null
  is_ambiguous: boolean
  notes: string | null
}

export interface Signal {
  id: string
  channel_id: string
  message_id: number
  signal_type: SignalType
  source: SignalSource
  direction: SignalDirection
  entry: number | null
  entry_low: number | null        // zone_estimated only
  entry_high: number | null       // zone_estimated only
  stop_loss: number | null
  take_profit_1: number | null
  take_profit_2: number | null
  take_profit_3: number | null
  raw_text: string
  parsed_at: string
  posted_at: string
  confidence: number              // 0–1
  outcome: SignalOutcome | null
  edits: MessageEdit[]
}

export interface ScreenshotClaim {
  id: string
  channel_id: string
  message_id: number
  claimed_direction: SignalDirection | null
  claimed_open: number | null
  claimed_close: number | null
  claimed_profit_pts: number | null
  claimed_open_time: string | null
  claimed_close_time: string | null
  verdict: ScreenshotVerdict
  posted_at: string
  notes: string | null
}

export interface NonSignalMessage {
  id: string
  channel_id: string
  message_id: number
  message_type: 'non_signal' | 'image_deferred'
  content: string | null
  posted_at: string
  is_deleted: boolean
  source: SignalSource
}

export interface ChannelDetail {
  channel: Channel
  score_breakdown: ScoreBreakdown
  signals: Signal[]
  screenshots: ScreenshotClaim[]
  non_signals: NonSignalMessage[]
}
