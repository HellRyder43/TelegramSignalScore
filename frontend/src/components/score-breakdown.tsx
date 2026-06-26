import type { ScoreBreakdown } from '@/lib/types'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { cn } from '@/lib/utils'

function fmt(n: number | null, decimals = 1): string {
  if (n === null) return '—'
  return n.toFixed(decimals)
}

function fmtPct(n: number | null): string {
  if (n === null) return '—'
  return `${n.toFixed(1)}%`
}

interface FactorRowProps {
  label: string
  detail: string
  points: number
  isNegative?: boolean
}

function FactorRow({ label, detail, points, isNegative }: FactorRowProps) {
  const isZero = points === 0
  const sign = points > 0 ? '+' : ''

  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm text-foreground">{label}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{detail}</p>
      </div>
      <span
        className={cn(
          'font-mono text-sm font-semibold tabular-nums flex-shrink-0',
          isZero && 'text-muted-foreground',
          !isZero && !isNegative && points > 0 && 'text-[--verdict-trusted]',
          (isNegative || points < 0) && 'text-[--verdict-avoid]',
        )}
      >
        {sign}{points}
      </span>
    </div>
  )
}

interface ScoreBreakdownPanelProps {
  breakdown: ScoreBreakdown
}

export function ScoreBreakdownPanel({ breakdown }: ScoreBreakdownPanelProps) {
  const { details } = breakdown

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-xs font-semibold text-foreground uppercase tracking-widest">
          Score Breakdown
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Raw performance factors */}
        <div className="divide-y divide-border/50">
          <FactorRow
            label="Verified Win Rate"
            detail={`${fmtPct(details.win_rate_pct)} on ${details.total_verified} signals (${details.wins}W / ${details.losses}L${details.ambiguous > 0 ? ` / ${details.ambiguous} ambiguous` : ''})`}
            points={breakdown.win_rate_component}
          />
          <FactorRow
            label="Risk:Reward Ratio"
            detail={`${fmt(details.avg_risk_reward)}:1 average across verified signals`}
            points={breakdown.rr_component}
          />
          <FactorRow
            label="Expectancy"
            detail={`${details.avg_points_per_trade !== null && details.avg_points_per_trade >= 0 ? '+' : ''}${fmt(details.avg_points_per_trade)} pts average per trade`}
            points={breakdown.expectancy_component}
          />
        </div>

        <Separator className="my-3" />

        {/* Sample weight */}
        <div className="flex items-center justify-between py-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground">Sample Confidence</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {details.total_verified} verified signals ({details.live_signal_count} live, {details.backfill_signal_count} backfilled)
              {' '}→ {Math.round(breakdown.sample_weight * 100)}% weight applied
            </p>
          </div>
          <span className="font-mono text-xs text-muted-foreground tabular-nums flex-shrink-0">
            ×{breakdown.sample_weight.toFixed(2)}
          </span>
        </div>

        <div className="flex items-center justify-between py-2 border-t border-border/50">
          <p className="text-sm text-foreground">Adjusted Performance</p>
          <span className="font-mono text-sm font-semibold tabular-nums">
            {breakdown.adjusted_performance}
          </span>
        </div>

        <Separator className="my-3" />

        {/* Integrity */}
        <div className="flex items-center justify-between py-2">
          <div className="min-w-0 flex-1">
            <p className="text-sm text-foreground">Integrity Score</p>
            <p className="text-xs text-muted-foreground mt-0.5">
              {details.post_move_edit_count} post-move edits,{' '}
              {details.delete_signal_count} deleted signals,{' '}
              {details.contradicted_screenshot_count} contradicted screenshots
            </p>
          </div>
          <span
            className={cn(
              'font-mono text-sm font-semibold tabular-nums flex-shrink-0',
              breakdown.integrity_score >= 20
                ? 'text-[--verdict-trusted]'
                : breakdown.integrity_score >= 10
                ? 'text-[--verdict-observe]'
                : 'text-[--verdict-avoid]',
            )}
          >
            {breakdown.integrity_score >= 0 ? '+' : ''}{breakdown.integrity_score}{' '}
            <span className="text-xs text-muted-foreground font-normal">/ 25</span>
          </span>
        </div>

        <Separator className="my-3" />

        {/* Final score */}
        <div className="flex items-center justify-between py-2">
          <p className="text-base font-bold text-foreground">Trust Score</p>
          <span className="font-mono text-lg font-bold tabular-nums text-primary">
            {breakdown.final_score}{' '}
            <span className="text-xs text-muted-foreground font-normal">/ 100</span>
          </span>
        </div>

        <div className="mt-3 bg-muted/60 rounded-lg p-3">
          <p className="text-[10px] text-muted-foreground leading-relaxed">
            Formula: (Win Rate + R:R + Expectancy) × Sample Confidence + Integrity Score.
            Weights are configurable in config.py and will be tuned as data accumulates.
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
