import type { Verdict } from '@/lib/types'
import { cn } from '@/lib/utils'

const VERDICT_CONFIG = {
  trusted: {
    label: 'Trusted',
    classes: 'bg-[--verdict-trusted]/15 text-[--verdict-trusted] border-[--verdict-trusted]/30',
  },
  caution: {
    label: 'Caution',
    classes: 'bg-[--verdict-caution]/15 text-[--verdict-caution] border-[--verdict-caution]/30',
  },
  observe: {
    label: 'Observe',
    classes: 'bg-[--verdict-observe]/15 text-[--verdict-observe] border-[--verdict-observe]/30',
  },
  avoid: {
    label: 'Avoid',
    classes: 'bg-[--verdict-avoid]/15 text-[--verdict-avoid] border-[--verdict-avoid]/30',
  },
} as const

interface VerdictBadgeProps {
  verdict: Verdict
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function VerdictBadge({ verdict, size = 'md', className }: VerdictBadgeProps) {
  const config = VERDICT_CONFIG[verdict]

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border font-semibold uppercase tracking-wide',
        size === 'sm' && 'px-2 py-0.5 text-[10px]',
        size === 'md' && 'px-2.5 py-0.5 text-[11px]',
        size === 'lg' && 'px-3 py-1 text-xs',
        config.classes,
        className,
      )}
    >
      {config.label}
    </span>
  )
}

export function verdictColor(verdict: Verdict): string {
  return VERDICT_CONFIG[verdict].classes
}
