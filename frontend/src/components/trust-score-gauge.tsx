import type { Verdict } from '@/lib/types'
import { cn } from '@/lib/utils'

function scoreToColor(verdict: Verdict): string {
  return {
    trusted: 'text-[--verdict-trusted]',
    caution: 'text-[--verdict-caution]',
    observe: 'text-[--verdict-observe]',
    avoid: 'text-[--verdict-avoid]',
  }[verdict]
}

function scoreToBarColor(verdict: Verdict): string {
  return {
    trusted: 'bg-[--verdict-trusted]',
    caution: 'bg-[--verdict-caution]',
    observe: 'bg-[--verdict-observe]',
    avoid: 'bg-[--verdict-avoid]',
  }[verdict]
}

interface TrustScoreGaugeProps {
  score: number
  verdict: Verdict
  size?: 'sm' | 'lg'
  className?: string
}

export function TrustScoreGauge({ score, verdict, size = 'sm', className }: TrustScoreGaugeProps) {
  const clampedScore = Math.max(0, Math.min(100, score))
  const barColor = scoreToBarColor(verdict)
  const textColor = scoreToColor(verdict)

  if (size === 'lg') {
    return (
      <div className={cn('flex flex-col gap-2', className)}>
        <div className="flex items-end gap-2">
          <span className={cn('font-mono text-5xl font-bold tabular-nums leading-none', textColor)}>
            {clampedScore}
          </span>
          <span className="mb-1 text-sm text-muted-foreground">/100</span>
        </div>
        <div className="h-2 w-full rounded-full bg-muted">
          <div
            className={cn('h-2 rounded-full transition-all', barColor)}
            style={{ width: `${clampedScore}%` }}
          />
        </div>
      </div>
    )
  }

  return (
    <div className={cn('flex items-center gap-2', className)}>
      <span className={cn('font-mono text-sm font-semibold tabular-nums w-8 text-right', textColor)}>
        {clampedScore}
      </span>
      <div className="h-1 flex-1 rounded-full bg-muted min-w-[60px]">
        <div
          className={cn('h-1 rounded-full', barColor)}
          style={{ width: `${clampedScore}%` }}
        />
      </div>
    </div>
  )
}
