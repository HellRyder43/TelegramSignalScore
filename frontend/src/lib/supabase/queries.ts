/**
 * Server-side Supabase query functions.
 * All functions use the server client (cookie-based, uses next/headers).
 * Import these only from Server Components or Server Actions.
 */

import { createClient } from './server'
import {
  transformChannel,
  transformBreakdown,
  transformMessageEdit,
  transformSignal,
  transformScreenshot,
  transformNonSignal,
  emptyBreakdown,
} from '@/lib/transforms'
import type { Channel, ChannelDetail, MessageEdit } from '@/lib/types'

export async function getChannels(): Promise<Channel[]> {
  const supabase = await createClient()
  const { data, error } = await supabase
    .from('channels')
    .select('*')
    .order('trust_score', { ascending: false })

  if (error) {
    console.error('[getChannels]', error.message)
    return []
  }
  return (data ?? []).map(transformChannel)
}

export async function getChannelDetail(id: string): Promise<ChannelDetail | null> {
  const supabase = await createClient()

  // ── 1. Channel row ──────────────────────────────────────────────────────────
  const { data: channelRow, error: chErr } = await supabase
    .from('channels')
    .select('*')
    .eq('id', id)
    .maybeSingle()

  if (chErr) {
    console.error('[getChannelDetail] channel lookup:', chErr.message)
    return null
  }
  if (!channelRow) return null

  const channel = transformChannel(channelRow)

  // ── 2. Score breakdown ──────────────────────────────────────────────────────
  const { data: breakdownRow } = await supabase
    .from('score_breakdowns')
    .select('*')
    .eq('channel_id', id)
    .maybeSingle()

  const score_breakdown = breakdownRow
    ? transformBreakdown(breakdownRow)
    : emptyBreakdown(id)

  // ── 3. Signals (with outcomes embedded via FK join) ─────────────────────────
  const { data: signalRows, error: sigErr } = await supabase
    .from('signals')
    .select('*, signal_outcomes(*)')
    .eq('channel_id', id)
    .order('posted_at', { ascending: false })
    .limit(100)

  if (sigErr) {
    console.error('[getChannelDetail] signals:', sigErr.message)
  }

  const rawSignals = signalRows ?? []

  // ── 4. Message edits for those signals ──────────────────────────────────────
  const editsMap = new Map<string, MessageEdit[]>()

  const messageIds = rawSignals
    .map((s) => s.message_id as string)
    .filter(Boolean)

  if (messageIds.length > 0) {
    const { data: editRows } = await supabase
      .from('message_edits')
      .select('*')
      .in('message_id', messageIds)
      .order('edit_number', { ascending: true })

    for (const row of editRows ?? []) {
      const msgId = String(row.message_id)
      if (!editsMap.has(msgId)) editsMap.set(msgId, [])
      editsMap.get(msgId)!.push(transformMessageEdit(row))
    }
  }

  const signals = rawSignals.map((row) => transformSignal(row, editsMap))

  // ── 5. Screenshot claims ────────────────────────────────────────────────────
  const { data: shotRows } = await supabase
    .from('screenshot_claims')
    .select('*')
    .eq('channel_id', id)
    .order('posted_at', { ascending: false })
    .limit(50)

  const screenshots = (shotRows ?? []).map(transformScreenshot)

  // ── 6. Non-signal messages ──────────────────────────────────────────────────
  const { data: nonSigRows } = await supabase
    .from('messages')
    .select('*')
    .eq('channel_id', id)
    .in('message_type', ['non_signal', 'image_deferred'])
    .order('posted_at', { ascending: false })
    .limit(50)

  const non_signals = (nonSigRows ?? []).map(transformNonSignal)

  return { channel, score_breakdown, signals, screenshots, non_signals }
}
