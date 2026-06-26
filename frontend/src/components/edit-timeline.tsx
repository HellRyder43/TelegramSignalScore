import type { MessageEdit } from '@/lib/types'
import { AlertTriangle } from 'lucide-react'
import { cn } from '@/lib/utils'

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
  })
}

interface EditTimelineProps {
  originalText: string
  postedAt: string
  edits: MessageEdit[]
}

export function EditTimeline({ originalText, postedAt, edits }: EditTimelineProps) {
  if (edits.length === 0) {
    return (
      <div className="flex items-start gap-3 py-2">
        <div className="mt-1 flex-shrink-0 w-2.5 h-2.5 rounded-full bg-muted-foreground/40" />
        <div className="min-w-0">
          <p className="text-[11px] text-muted-foreground mb-1">{formatTime(postedAt)} — Original</p>
          <pre className="text-xs text-foreground whitespace-pre-wrap break-all font-mono leading-relaxed">
            {originalText}
          </pre>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-0">
      {/* Original */}
      <div className="flex items-start gap-3 py-2">
        <div className="flex flex-col items-center">
          <div className="mt-1 flex-shrink-0 w-2.5 h-2.5 rounded-full bg-muted-foreground/40" />
          <div className="w-px flex-1 bg-border mt-1" style={{ minHeight: '20px' }} />
        </div>
        <div className="min-w-0 pb-2">
          <p className="text-[11px] text-muted-foreground mb-1">{formatTime(postedAt)} — Original</p>
          <pre className="text-xs text-foreground whitespace-pre-wrap break-all font-mono leading-relaxed">
            {originalText}
          </pre>
        </div>
      </div>

      {/* Edits */}
      {edits.map((edit, i) => {
        const isLast = i === edits.length - 1
        const isPostMove = edit.is_post_move_edit

        return (
          <div key={edit.id} className="flex items-start gap-3 py-2">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  'mt-1 flex-shrink-0 w-2.5 h-2.5 rounded-full',
                  isPostMove ? 'bg-[--verdict-avoid]' : 'bg-primary',
                )}
              />
              {!isLast && (
                <div className="w-px flex-1 bg-border mt-1" style={{ minHeight: '20px' }} />
              )}
            </div>
            <div className="min-w-0 pb-2 flex-1">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-[11px] text-muted-foreground">
                  {formatTime(edit.edited_at)} — Edit #{edit.edit_number}
                </p>
                {isPostMove && (
                  <span className="inline-flex items-center gap-1 rounded-full border border-[--verdict-avoid]/30 bg-[--verdict-avoid]/10 px-1.5 py-0.5 text-[10px] text-[--verdict-avoid]">
                    <AlertTriangle className="w-2.5 h-2.5" />
                    Post-move edit
                  </span>
                )}
              </div>
              <pre className="text-xs text-foreground whitespace-pre-wrap break-all font-mono leading-relaxed">
                {edit.content_after}
              </pre>
            </div>
          </div>
        )
      })}
    </div>
  )
}
