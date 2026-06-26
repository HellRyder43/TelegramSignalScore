import { getMockChannels } from '@/lib/mock-data'
import { ChannelsTable } from '@/components/channels-table'
import { ShieldCheck } from 'lucide-react'

export default function HomePage() {
  const channels = getMockChannels()

  const totalVerified = channels.reduce((s, c) => s + c.sample_size, 0)
  const trusted = channels.filter((c) => c.verdict === 'trusted').length
  const avoid = channels.filter((c) => c.verdict === 'avoid').length

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
          <time className="text-xs text-muted-foreground">
            {new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
          </time>
        </div>
      </header>

      {/* Main */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-8">
        {/* Summary stats — unified surface */}
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
          <ChannelsTable channels={channels} />
        </div>
      </main>

      {/* Footer disclaimer */}
      <footer className="border-t border-border px-6 py-4">
        <p className="mx-auto max-w-7xl text-[10px] text-muted-foreground leading-relaxed">
          <strong className="font-medium text-muted-foreground">Disclaimer:</strong>{' '}
          Scores reflect past, broker-specific verification only (RoboForex XAUUSD feed) and are not trading advice.
          Outcome data is derived from MT5 1-minute candles on my own account. Results on other brokers may differ.
          Small sample sizes are indicated by a dampened score. This tool measures channel honesty, not guaranteed future performance.
        </p>
      </footer>
    </div>
  )
}
