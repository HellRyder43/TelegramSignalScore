import { notFound } from 'next/navigation'
import Link from 'next/link'
import { getMockChannelDetail } from '@/lib/mock-data'
import { VerdictBadge } from '@/components/verdict-badge'
import { TrustScoreGauge } from '@/components/trust-score-gauge'
import { ScoreBreakdownPanel } from '@/components/score-breakdown'
import { RedFlagsPanel } from '@/components/red-flags-panel'
import { SignalHistory } from '@/components/signal-history'
import { ShieldCheck, ArrowLeft, Users } from 'lucide-react'
import { cn } from '@/lib/utils'

export default async function ChannelDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const detail = getMockChannelDetail(id)

  if (!detail) notFound()

  const { channel, score_breakdown, signals, screenshots, non_signals } = detail

  function fmtPct(n: number | null): string {
    if (n === null) return '—'
    return `${(n * 100).toFixed(1)}%`
  }

  function fmtPts(n: number): string {
    return `${n >= 0 ? '+' : ''}${n} pts`
  }

  function fmt(n: number | null, dec = 1): string {
    if (n === null) return '—'
    return n.toFixed(dec)
  }

  return (
    <div className="flex flex-col min-h-screen">
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-card/80 backdrop-blur-sm px-6 py-4">
        <div className="mx-auto max-w-7xl flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="bg-primary/10 rounded-lg p-1.5">
              <ShieldCheck className="w-4 h-4 text-primary" />
            </div>
            <span className="font-semibold text-sm tracking-tight text-foreground">
              XAUUSD Signal Trust Score
            </span>
          </div>
        </div>
      </header>

      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-8">
        {/* Back */}
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground hover:underline transition-colors mb-6"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          All channels
        </Link>

        {/* Channel hero */}
        <div className="rounded-xl border border-border bg-card shadow-sm p-6 mb-6">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
            {/* Name + meta */}
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <h1 className="text-xl font-bold text-foreground">{channel.name}</h1>
                <VerdictBadge verdict={channel.verdict} size="lg" />
              </div>
              <div className="flex items-center gap-3 flex-wrap text-xs text-muted-foreground">
                {channel.username && <span>@{channel.username.replace(/^@/, '')}</span>}
                {channel.member_count !== null && (
                  <span className="flex items-center gap-1">
                    <Users className="w-3 h-3" />
                    {channel.member_count.toLocaleString()} members
                  </span>
                )}
              </div>
            </div>

            {/* Score gauge */}
            <div className="flex-shrink-0 min-w-[180px]">
              <TrustScoreGauge
                score={channel.trust_score}
                verdict={channel.verdict}
                size="lg"
              />
            </div>
          </div>

          {/* Quick stats — 2 rows of 4 */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-4">
            {[
              { label: 'Win Rate', value: fmtPct(channel.verified_win_rate), mono: true },
              { label: 'Verified n', value: String(channel.sample_size), mono: true },
              { label: 'Total Pts', value: fmtPts(channel.total_points), mono: true, colored: true, val: channel.total_points },
              { label: 'Avg R:R', value: fmt(channel.avg_risk_reward), mono: true },
              { label: 'Edits', value: String(channel.edit_count), mono: true, warn: channel.edit_count > 10 },
              { label: 'Deletes', value: String(channel.delete_count), mono: true, danger: channel.delete_count > 5 },
              { label: 'Screenshots', value: null, mono: true, screenshotStat: true },
              {
                label: 'Last signal',
                value: channel.last_signal_at
                  ? new Date(channel.last_signal_at).toLocaleDateString('en-GB', {
                      day: '2-digit',
                      month: 'short',
                      timeZone: 'UTC',
                    })
                  : '—',
                mono: false,
              },
            ].map(({ label, value, mono, colored, val, warn, danger, screenshotStat }) => (
              <div key={label} className="rounded-lg border border-border bg-muted/40 px-4 py-3">
                <p className="text-[10px] text-muted-foreground uppercase tracking-widest mb-1">{label}</p>
                {screenshotStat ? (
                  <p className="font-mono text-sm font-semibold">
                    <span className="text-[--verdict-trusted]">{channel.screenshot_confirmed}</span>
                    <span className="text-muted-foreground/60 mx-1">/</span>
                    <span className={channel.screenshot_contradicted > 0 ? 'text-[--verdict-avoid]' : 'text-muted-foreground'}>
                      {channel.screenshot_contradicted}
                    </span>
                    <span className="text-[10px] text-muted-foreground font-normal ml-1">confirmed/bad</span>
                  </p>
                ) : (
                  <p
                    className={cn(
                      mono ? 'font-mono' : '',
                      'text-sm font-semibold',
                      colored && val !== undefined ? (val >= 0 ? 'text-[--verdict-trusted]' : 'text-[--verdict-avoid]') : '',
                      warn ? 'text-[--verdict-observe]' : '',
                      danger ? 'text-[--verdict-avoid]' : '',
                      !colored && !warn && !danger ? 'text-foreground' : '',
                    )}
                  >
                    {value}
                  </p>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Two-column layout: breakdown + flags | signal history */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
          {/* Left column */}
          <div className="flex flex-col gap-6">
            <ScoreBreakdownPanel breakdown={score_breakdown} />
            <RedFlagsPanel breakdown={score_breakdown} />
          </div>

          {/* Right column: signal history */}
          <div>
            <h2 className="text-sm font-semibold text-foreground mb-4">Signal History</h2>
            <SignalHistory signals={signals} screenshots={screenshots} nonSignals={non_signals} />
            {signals.length === 0 && screenshots.length === 0 && non_signals.length === 0 && (
              <p className="text-sm text-muted-foreground mt-2">
                No signal history in mock data for this channel yet. Only ch_001 (XAUUSD Elite Signals) has full detail data.
              </p>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border px-6 py-4 mt-8">
        <p className="mx-auto max-w-7xl text-[10px] text-muted-foreground leading-relaxed">
          <strong className="font-medium text-muted-foreground">Disclaimer:</strong>{' '}
          Scores reflect past, broker-specific verification only (RoboForex XAUUSD feed) and are not trading advice.
        </p>
      </footer>
    </div>
  )
}
