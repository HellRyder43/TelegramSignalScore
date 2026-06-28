'use client'

/**
 * Client component that wraps the channel overview table with a Supabase
 * Realtime subscription. When any row in the `channels` table changes, it
 * re-fetches and re-renders without a page reload.
 *
 * Also renders the summary stats (which update live along with the table).
 */

import { useState, useEffect, useCallback } from 'react'
import { createClient } from '@/lib/supabase/client'
import { transformChannel } from '@/lib/transforms'
import { ChannelsTable } from '@/components/channels-table'
import type { Channel } from '@/lib/types'

interface Props {
  initialChannels: Channel[]
}

export function ChannelsRealtime({ initialChannels }: Props) {
  const [channels, setChannels] = useState<Channel[]>(initialChannels)

  const refresh = useCallback(async () => {
    const supabase = createClient()
    const { data } = await supabase
      .from('channels')
      .select('*')
      .order('trust_score', { ascending: false })
    if (data) setChannels(data.map(transformChannel))
  }, [])

  useEffect(() => {
    const supabase = createClient()
    const sub = supabase
      .channel('channels-live')
      .on(
        'postgres_changes',
        { event: '*', schema: 'public', table: 'channels' },
        refresh,
      )
      .subscribe()

    return () => { supabase.removeChannel(sub) }
  }, [refresh])

  const totalVerified = channels.reduce((s, c) => s + c.sample_size, 0)
  const trusted = channels.filter((c) => c.verdict === 'trusted').length
  const avoid = channels.filter((c) => c.verdict === 'avoid').length

  return (
    <>
      {/* Summary stats */}
      <div className="rounded-xl border border-border bg-card shadow-sm mb-8 overflow-hidden">
        <div className="grid grid-cols-2 sm:grid-cols-4 divide-y sm:divide-y-0 sm:divide-x divide-border">
          <div className="px-6 py-5">
            <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1.5">Channels tracked</p>
            <p className="font-mono text-3xl font-bold text-foreground">{channels.length}</p>
          </div>
          <div className="px-6 py-5">
            <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1.5">Verified signals</p>
            <p className="font-mono text-3xl font-bold text-foreground">{totalVerified}</p>
          </div>
          <div className="px-6 py-5">
            <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1.5">Trusted channels</p>
            <p className="font-mono text-3xl font-bold text-[--verdict-trusted]">{trusted}</p>
          </div>
          <div className="px-6 py-5">
            <p className="text-[11px] text-muted-foreground uppercase tracking-widest mb-1.5">Avoid</p>
            <p className="font-mono text-3xl font-bold text-[--verdict-avoid]">{avoid}</p>
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-border bg-card shadow-sm overflow-hidden">
        <div className="px-6 pt-5 pb-3">
          <h1 className="text-base font-semibold text-foreground">Channel Rankings</h1>
          <p className="text-xs text-muted-foreground mt-0.5">
            Click any column header to sort. Click a row to see the full signal history and score breakdown.
          </p>
        </div>

        {channels.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <p className="text-sm font-medium text-foreground mb-2">No channels tracked yet</p>
            <p className="text-xs text-muted-foreground max-w-md mx-auto leading-relaxed">
              Run <code className="bg-muted px-1 rounded text-[11px]">python scripts/list_channels.py</code> to find your channel IDs, then add them to{' '}
              <code className="bg-muted px-1 rounded text-[11px]">TRACKED_CHANNEL_IDS</code> in <code className="bg-muted px-1 rounded text-[11px]">.env</code>{' '}
              and start the ingestor.
            </p>
          </div>
        ) : (
          <ChannelsTable channels={channels} />
        )}
      </div>
    </>
  )
}
