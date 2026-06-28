import { getChannels } from '@/lib/supabase/queries'
import { ChannelsRealtime } from '@/components/channels-realtime'
import { ShieldCheck } from 'lucide-react'

export default async function HomePage() {
  const channels = await getChannels()

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

      {/* Main — stats + table rendered by ChannelsRealtime (updates live) */}
      <main className="flex-1 mx-auto w-full max-w-7xl px-6 py-8">
        <ChannelsRealtime initialChannels={channels} />
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
