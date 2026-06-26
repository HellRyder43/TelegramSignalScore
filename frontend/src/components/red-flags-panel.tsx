import type { ScoreBreakdown } from '@/lib/types'
import { AlertTriangle, Trash2, Camera } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface RedFlag {
  icon: React.ReactNode
  label: string
  count: number
  severity: 'critical' | 'warning' | 'info'
  description: string
}

function severityClass(severity: RedFlag['severity']) {
  return {
    critical: 'text-[--verdict-avoid] border-[--verdict-avoid]/30 bg-[--verdict-avoid]/10',
    warning: 'text-[--verdict-observe] border-[--verdict-observe]/30 bg-[--verdict-observe]/10',
    info: 'text-[--verdict-caution] border-[--verdict-caution]/30 bg-[--verdict-caution]/10',
  }[severity]
}

interface RedFlagsPanelProps {
  breakdown: ScoreBreakdown
}

export function RedFlagsPanel({ breakdown }: RedFlagsPanelProps) {
  const { details } = breakdown
  const flags: RedFlag[] = []

  if (details.contradicted_screenshot_count > 0) {
    flags.push({
      icon: <Camera className="w-4 h-4" />,
      label: 'Fabricated screenshots',
      count: details.contradicted_screenshot_count,
      severity: 'critical',
      description:
        'MT5 screenshot shows a trade that could not have occurred — price never reached the claimed levels.',
    })
  }

  if (details.post_move_edit_count > 0) {
    flags.push({
      icon: <AlertTriangle className="w-4 h-4" />,
      label: 'Post-move edits',
      count: details.post_move_edit_count,
      severity: details.post_move_edit_count >= 3 ? 'critical' : 'warning',
      description:
        'Signal levels were changed after price had already moved past the original entry. This misrepresents the original trade plan.',
    })
  }

  if (details.delete_signal_count > 0) {
    flags.push({
      icon: <Trash2 className="w-4 h-4" />,
      label: 'Deleted signals',
      count: details.delete_signal_count,
      severity: details.delete_signal_count >= 5 ? 'critical' : 'warning',
      description:
        'Forward signals were deleted after posting. Deleting losers inflates the apparent win rate.',
    })
  }

  if (details.edit_count > 0 && details.post_move_edit_count === 0) {
    flags.push({
      icon: <AlertTriangle className="w-4 h-4" />,
      label: 'Minor edits',
      count: details.edit_count,
      severity: 'info',
      description:
        'Signal messages were edited. None were flagged as post-move, but edits after posting reduce confidence.',
    })
  }

  if (flags.length === 0) {
    return (
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle className="text-xs font-semibold text-foreground uppercase tracking-widest">
            Red Flags
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            No integrity violations detected in verified signals.
          </p>
        </CardContent>
      </Card>
    )
  }

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle className="text-xs font-semibold text-foreground uppercase tracking-widest">
          Red Flags
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {flags.map((flag) => (
          <div
            key={flag.label}
            className={`flex items-start gap-3 rounded-lg border p-3.5 ${severityClass(flag.severity)}`}
          >
            <span className="mt-0.5 flex-shrink-0">{flag.icon}</span>
            <div className="min-w-0">
              <p className="text-sm font-medium">
                {flag.label}{' '}
                <span className="font-mono text-sm font-bold">×{flag.count}</span>
              </p>
              <p className="mt-0.5 text-xs opacity-80">{flag.description}</p>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  )
}
