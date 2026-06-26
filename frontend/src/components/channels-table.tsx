'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import type { Channel } from '@/lib/types'
import { VerdictBadge } from '@/components/verdict-badge'
import { TrustScoreGauge } from '@/components/trust-score-gauge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { cn } from '@/lib/utils'

type SortKey = keyof Channel
type SortDir = 'asc' | 'desc'

function fmt(n: number | null, decimals = 1): string {
  if (n === null) return '—'
  return n.toFixed(decimals)
}

function fmtPct(n: number | null): string {
  if (n === null) return '—'
  return `${(n * 100).toFixed(1)}%`
}

function fmtPts(n: number): string {
  return `${n >= 0 ? '+' : ''}${n}`
}

function fmtDate(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'UTC',
  })
}

function SortIcon({ col, sortKey, dir }: { col: SortKey; sortKey: SortKey; dir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown className="ml-1 inline w-3 h-3 text-muted-foreground/50" />
  return dir === 'asc'
    ? <ChevronUp className="ml-1 inline w-3 h-3 text-primary" />
    : <ChevronDown className="ml-1 inline w-3 h-3 text-primary" />
}

interface ColumnDef {
  key: SortKey
  label: string
  align?: 'right' | 'left'
  sortable?: boolean
}

const COLUMNS: ColumnDef[] = [
  { key: 'name', label: 'Channel', align: 'left', sortable: true },
  { key: 'trust_score', label: 'Trust Score', align: 'left', sortable: true },
  { key: 'verdict', label: 'Verdict', sortable: true },
  { key: 'verified_win_rate', label: 'Win Rate', align: 'right', sortable: true },
  { key: 'sample_size', label: 'n', align: 'right', sortable: true },
  { key: 'total_points', label: 'Total Pts', align: 'right', sortable: true },
  { key: 'avg_risk_reward', label: 'Avg R:R', align: 'right', sortable: true },
  { key: 'edit_count', label: 'Edits', align: 'right', sortable: true },
  { key: 'delete_count', label: 'Deletes', align: 'right', sortable: true },
  { key: 'last_signal_at', label: 'Last Signal', align: 'right', sortable: true },
]

interface ChannelsTableProps {
  channels: Channel[]
}

export function ChannelsTable({ channels }: ChannelsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('trust_score')
  const [sortDir, setSortDir] = useState<SortDir>('desc')

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  const sorted = useMemo(() => {
    return [...channels].sort((a, b) => {
      const av = a[sortKey]
      const bv = b[sortKey]
      if (av === null || av === undefined) return 1
      if (bv === null || bv === undefined) return -1
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [channels, sortKey, sortDir])

  return (
    <Table>
      <TableHeader>
        <TableRow>
          {COLUMNS.map((col) => (
            <TableHead
              key={col.key}
              className={cn(
                col.align === 'right' ? 'text-right' : '',
                col.sortable ? 'cursor-pointer select-none hover:text-foreground transition-colors' : '',
                'text-xs font-medium text-muted-foreground uppercase tracking-wider',
              )}
              onClick={col.sortable ? () => handleSort(col.key) : undefined}
            >
              {col.label}
              {col.sortable && <SortIcon col={col.key} sortKey={sortKey} dir={sortDir} />}
            </TableHead>
          ))}
        </TableRow>
      </TableHeader>
      <TableBody>
        {sorted.map((ch) => (
          <TableRow
            key={ch.id}
            className="group cursor-pointer hover:bg-muted/40 transition-colors border-l-2 border-l-transparent hover:border-l-primary"
          >
            <TableCell className="py-3.5">
              <Link href={`/channel/${ch.id}`} className="block">
                <p className="font-semibold text-sm text-foreground">{ch.name}</p>
                {ch.username && (
                  <p className="text-xs text-muted-foreground/70">@{ch.username.replace(/^@/, '')}</p>
                )}
              </Link>
            </TableCell>
            <TableCell className="py-3.5">
              <Link href={`/channel/${ch.id}`} className="block">
                <TrustScoreGauge score={ch.trust_score} verdict={ch.verdict} />
              </Link>
            </TableCell>
            <TableCell className="py-3.5">
              <Link href={`/channel/${ch.id}`} className="block">
                <VerdictBadge verdict={ch.verdict} />
              </Link>
            </TableCell>
            <TableCell className="py-3.5 text-right font-mono text-sm tabular-nums">
              <Link href={`/channel/${ch.id}`} className="block">
                {fmtPct(ch.verified_win_rate)}
              </Link>
            </TableCell>
            <TableCell className="py-3.5 text-right font-mono text-sm tabular-nums text-muted-foreground">
              <Link href={`/channel/${ch.id}`} className="block">
                {ch.sample_size}
              </Link>
            </TableCell>
            <TableCell
              className={cn(
                'py-3.5 text-right font-mono text-sm tabular-nums',
                ch.total_points >= 0 ? 'text-[--verdict-trusted]' : 'text-[--verdict-avoid]',
              )}
            >
              <Link href={`/channel/${ch.id}`} className="block">
                {fmtPts(ch.total_points)}
              </Link>
            </TableCell>
            <TableCell className="py-3.5 text-right font-mono text-sm tabular-nums text-muted-foreground">
              <Link href={`/channel/${ch.id}`} className="block">
                {fmt(ch.avg_risk_reward)}
              </Link>
            </TableCell>
            <TableCell
              className={cn(
                'py-3.5 text-right font-mono text-sm tabular-nums',
                ch.edit_count > 10 ? 'text-[--verdict-observe]' : 'text-muted-foreground',
              )}
            >
              <Link href={`/channel/${ch.id}`} className="block">
                {ch.edit_count}
              </Link>
            </TableCell>
            <TableCell
              className={cn(
                'py-3.5 text-right font-mono text-sm tabular-nums',
                ch.delete_count > 5 ? 'text-[--verdict-avoid]' : 'text-muted-foreground',
              )}
            >
              <Link href={`/channel/${ch.id}`} className="block">
                {ch.delete_count}
              </Link>
            </TableCell>
            <TableCell className="py-3.5 text-right text-xs text-muted-foreground">
              <Link href={`/channel/${ch.id}`} className="block">
                {fmtDate(ch.last_signal_at)}
              </Link>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
