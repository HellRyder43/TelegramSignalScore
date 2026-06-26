'use client'

import { useState } from 'react'
import type { Signal, ScreenshotClaim, NonSignalMessage } from '@/lib/types'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { EditTimeline } from '@/components/edit-timeline'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

function formatDate(iso: string) {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  })
}

function OutcomeBadge({ outcome }: { outcome: Signal['outcome'] }) {
  if (!outcome) {
    return (
      <span className="inline-flex items-center rounded-full border border-muted-foreground/30 px-1.5 py-0.5 text-[10px] text-muted-foreground">
        Unresolved
      </span>
    )
  }
  const config = {
    win: 'bg-[--verdict-trusted]/15 text-[--verdict-trusted] border-[--verdict-trusted]/30',
    loss: 'bg-[--verdict-avoid]/15 text-[--verdict-avoid] border-[--verdict-avoid]/30',
    ambiguous_loss: 'bg-[--verdict-caution]/15 text-[--verdict-caution] border-[--verdict-caution]/30',
    unresolved: 'border-muted-foreground/30 text-muted-foreground',
  }[outcome.outcome]

  const label = {
    win: 'WIN',
    loss: 'LOSS',
    ambiguous_loss: 'AMBIGUOUS',
    unresolved: 'UNRESOLVED',
  }[outcome.outcome]

  const points =
    outcome.points !== null
      ? `${outcome.points >= 0 ? '+' : ''}${outcome.points} pts`
      : null

  return (
    <div className="flex items-center gap-1.5">
      <span className={cn('inline-flex items-center rounded-full border px-1.5 py-0.5 text-[10px] font-semibold', config)}>
        {label}
      </span>
      {points && (
        <span className={cn('font-mono text-xs tabular-nums', outcome.points && outcome.points >= 0 ? 'text-[--verdict-trusted]' : 'text-[--verdict-avoid]')}>
          {points}
        </span>
      )}
    </div>
  )
}

function SignalRow({ signal }: { signal: Signal }) {
  const [expanded, setExpanded] = useState(false)
  const hasEdits = signal.edits.length > 0
  const isZone = signal.signal_type === 'zone_estimated'
  const isBackfill = signal.source === 'backfill'

  return (
    <div className="border-b border-border last:border-0">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left px-4 py-3 hover:bg-muted/50 transition-colors cursor-pointer"
        aria-expanded={expanded}
      >
        <div className="flex items-start gap-3">
          {/* Direction */}
          <span
            className={cn(
              'flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold tabular-nums border',
              signal.direction === 'BUY'
                ? 'bg-[--verdict-trusted]/15 text-[--verdict-trusted] border-[--verdict-trusted]/30'
                : 'bg-[--verdict-avoid]/15 text-[--verdict-avoid] border-[--verdict-avoid]/30',
            )}
          >
            {signal.direction}
          </span>

          {/* Levels */}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              {isZone ? (
                <span className="font-mono text-xs text-foreground">
                  Entry zone: {signal.entry_low}–{signal.entry_high}
                </span>
              ) : (
                <span className="font-mono text-xs text-foreground">
                  {signal.entry}
                </span>
              )}
              {signal.stop_loss !== null && (
                <span className="font-mono text-xs text-[--verdict-avoid]">
                  SL {signal.stop_loss}
                </span>
              )}
              {signal.take_profit_1 !== null && (
                <span className="font-mono text-xs text-[--verdict-trusted]">
                  TP1 {signal.take_profit_1}
                </span>
              )}
              {signal.take_profit_2 !== null && (
                <span className="font-mono text-xs text-[--verdict-trusted]/70">
                  TP2 {signal.take_profit_2}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1.5 flex-wrap">
              <span className="text-[10px] text-muted-foreground">{formatDate(signal.posted_at)}</span>
              {isBackfill && (
                <span className="text-[10px] border border-muted-foreground/30 rounded-full px-1.5 text-muted-foreground">
                  backfilled
                </span>
              )}
              {isZone && (
                <span className="text-[10px] border border-accent/40 rounded-full px-1.5 text-accent/80">
                  zone estimated
                </span>
              )}
              {hasEdits && (
                <span className="text-[10px] border border-[--verdict-observe]/40 rounded-full px-1.5 text-[--verdict-observe]">
                  edited ×{signal.edits.length}
                </span>
              )}
              {signal.edits.some((e) => e.is_post_move_edit) && (
                <span className="text-[10px] border border-[--verdict-avoid]/40 rounded-full px-1.5 text-[--verdict-avoid] font-semibold">
                  post-move edit
                </span>
              )}
            </div>
          </div>

          {/* Outcome */}
          <div className="flex-shrink-0">
            <OutcomeBadge outcome={signal.outcome} />
          </div>

          {/* Expand icon */}
          <span className="flex-shrink-0 text-muted-foreground mt-0.5">
            {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="px-4 pb-4 bg-muted/40 border-t border-border">
          {/* Raw text */}
          <div className="mb-3">
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              Raw message text
            </p>
            <pre className="text-xs font-mono text-foreground whitespace-pre-wrap bg-background/50 rounded p-2 border border-border">
              {signal.raw_text}
            </pre>
          </div>

          {/* Outcome notes */}
          {signal.outcome?.notes && (
            <div className="mb-3">
              <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                Verification note
              </p>
              <p className="text-xs text-muted-foreground">{signal.outcome.notes}</p>
              {signal.outcome.candles_walked !== null && (
                <p className="text-[10px] text-muted-foreground/60 mt-0.5">
                  {signal.outcome.candles_walked} M1 candles walked
                </p>
              )}
            </div>
          )}

          {/* Edit history */}
          <div>
            <p className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
              Edit history
            </p>
            <div className="bg-muted/40 rounded border border-border p-2">
              <EditTimeline
                originalText={signal.raw_text}
                postedAt={signal.posted_at}
                edits={signal.edits}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ScreenshotRow({ ss }: { ss: ScreenshotClaim }) {
  const config = {
    confirmed: 'bg-[--verdict-trusted]/15 text-[--verdict-trusted] border-[--verdict-trusted]/30',
    contradicted: 'bg-[--verdict-avoid]/15 text-[--verdict-avoid] border-[--verdict-avoid]/30',
    unverifiable: 'border-muted-foreground/30 text-muted-foreground',
  }[ss.verdict]

  const label = {
    confirmed: 'CONFIRMED',
    contradicted: 'CONTRADICTED',
    unverifiable: 'UNVERIFIABLE',
  }[ss.verdict]

  return (
    <div className="flex items-start gap-3 px-4 py-3 border-b border-border last:border-0">
      <span
        className={cn(
          'flex-shrink-0 rounded-full border px-1.5 py-0.5 text-[10px] font-semibold',
          config,
        )}
      >
        {label}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          {ss.claimed_direction && (
            <span className="text-xs text-muted-foreground">{ss.claimed_direction}</span>
          )}
          {ss.claimed_open !== null && ss.claimed_close !== null && (
            <span className="font-mono text-xs text-foreground">
              {ss.claimed_open} → {ss.claimed_close}
            </span>
          )}
          {ss.claimed_profit_pts !== null && (
            <span className="font-mono text-xs text-[--verdict-trusted]">
              +{ss.claimed_profit_pts} pts
            </span>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground mt-1">{formatDate(ss.posted_at)}</p>
        {ss.notes && (
          <p className="text-xs text-muted-foreground/80 mt-1">{ss.notes}</p>
        )}
      </div>
    </div>
  )
}

function NonSignalRow({ msg }: { msg: NonSignalMessage }) {
  return (
    <div className="px-4 py-3 border-b border-border last:border-0">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] text-muted-foreground">{formatDate(msg.posted_at)}</span>
        {msg.is_deleted && (
          <span className="text-[10px] border border-[--verdict-avoid]/30 rounded-full px-1.5 text-[--verdict-avoid]">
            deleted
          </span>
        )}
        {msg.message_type === 'image_deferred' && (
          <span className="text-[10px] border border-muted-foreground/30 rounded-full px-1.5 text-muted-foreground">
            image (deferred)
          </span>
        )}
      </div>
      {msg.content && (
        <p className="text-sm text-muted-foreground">{msg.content}</p>
      )}
    </div>
  )
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex items-center justify-center h-24 text-sm text-muted-foreground">
      No {label} recorded yet.
    </div>
  )
}

interface SignalHistoryProps {
  signals: Signal[]
  screenshots: ScreenshotClaim[]
  nonSignals: NonSignalMessage[]
}

export function SignalHistory({ signals, screenshots, nonSignals }: SignalHistoryProps) {
  const textSignals = signals.filter((s) => s.signal_type === 'text')
  const zoneSignals = signals.filter((s) => s.signal_type === 'zone_estimated')

  return (
    <Tabs defaultValue="text">
      <TabsList className="mb-4">
        <TabsTrigger value="text">
          Stated-text
          {textSignals.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 h-4">
              {textSignals.length}
            </Badge>
          )}
        </TabsTrigger>
        <TabsTrigger value="zone">
          Zone-estimated
          {zoneSignals.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 h-4">
              {zoneSignals.length}
            </Badge>
          )}
        </TabsTrigger>
        <TabsTrigger value="screenshots">
          Screenshots
          {screenshots.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 h-4">
              {screenshots.length}
            </Badge>
          )}
        </TabsTrigger>
        <TabsTrigger value="other">
          Other posts
          {nonSignals.length > 0 && (
            <Badge variant="secondary" className="ml-1.5 text-[10px] px-1.5 h-4">
              {nonSignals.length}
            </Badge>
          )}
        </TabsTrigger>
      </TabsList>

      <TabsContent value="text">
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {textSignals.length === 0 ? (
            <EmptyState label="stated-text signals" />
          ) : (
            textSignals.map((s) => <SignalRow key={s.id} signal={s} />)
          )}
        </div>
        {textSignals.length > 0 && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            Stated-text signals have explicitly stated entry, SL, and TP levels. These are the primary input for trust score calculation.
          </p>
        )}
      </TabsContent>

      <TabsContent value="zone">
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {zoneSignals.length === 0 ? (
            <EmptyState label="zone-estimated signals" />
          ) : (
            zoneSignals.map((s) => <SignalRow key={s.id} signal={s} />)
          )}
        </div>
        {zoneSignals.length > 0 && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            Zone-estimated signals have levels inferred from chart images. Entry, SL, and TP are approximate.
            These are tracked and scored separately and weighted less than stated-text signals.
          </p>
        )}
      </TabsContent>

      <TabsContent value="screenshots">
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {screenshots.length === 0 ? (
            <EmptyState label="screenshot claims" />
          ) : (
            screenshots.map((ss) => <ScreenshotRow key={ss.id} ss={ss} />)
          )}
        </div>
        {screenshots.length > 0 && (
          <p className="mt-2 text-[10px] text-muted-foreground">
            Screenshots show past trades and feed the integrity score only — never the win rate. A contradicted screenshot means price never reached the claimed level.
          </p>
        )}
      </TabsContent>

      <TabsContent value="other">
        <div className="rounded-lg border border-border bg-card overflow-hidden">
          {nonSignals.length === 0 ? (
            <EmptyState label="non-signal messages" />
          ) : (
            nonSignals.map((msg) => <NonSignalRow key={msg.id} msg={msg} />)
          )}
        </div>
      </TabsContent>
    </Tabs>
  )
}
