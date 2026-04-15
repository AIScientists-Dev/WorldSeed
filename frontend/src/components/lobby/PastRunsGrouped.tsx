/* WorldSeed — PastRunsGrouped: past runs grouped by scene_id.
 *
 * Structure: Accordion (shadcn) + ScrollArea for long lists.
 * Design: time-first rows, demoted hex IDs, single LIVE indicator,
 * clear hierarchy between section title / group headers / run rows.
 */

import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from '@/components/ui/accordion'
import { ScrollArea } from '@/components/ui/scroll-area'
import { humanize } from '@/lib/helpers'

// ── Types ──

interface Run {
  run_id: string
  scene_id: string
  start_time?: string
  tick_count?: number
  agent_count?: number
  dm_calls?: number
}

interface Group {
  sceneId: string
  runs: Run[]
  latestTime: number
  hasLive: boolean
}

// ── Pure formatting helpers ──

const MAX_VISIBLE = 8

function relativeTime(iso: string | undefined, t: (key: string, opts?: any) => string): string {
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  const min = Math.floor(diff / 60000)
  if (min < 1) return t('time.justNow')
  if (min < 60) return t('time.minutesAgo', { count: min })
  const hr = Math.floor(min / 60)
  if (hr < 24) return t('time.hoursAgo', { count: hr })
  const d = Math.floor(hr / 24)
  if (d === 1) return t('time.yesterday')
  if (d < 30) return t('time.daysAgo', { count: d })
  return t('time.monthsAgo', { count: Math.floor(d / 30) })
}

function runStats(run: Run, t: (key: string, opts?: any) => string): string {
  const parts: string[] = []
  if (run.tick_count && run.tick_count > 0) parts.push(t('stats.ticks', { count: run.tick_count }))
  if (run.agent_count && run.agent_count > 0) parts.push(t('stats.agents', { count: run.agent_count }))
  if (run.dm_calls && run.dm_calls > 0) parts.push(t('stats.dmCalls', { count: run.dm_calls }))
  return parts.join(' \u00b7 ')
}

function groupRuns(runs: Run[], currentRunId: string): Group[] {
  const map: Record<string, Run[]> = {}
  for (const r of runs) {
    const key = r.scene_id || '(unknown)'
    ;(map[key] = map[key] || []).push(r)
  }
  return Object.entries(map)
    .map(([sceneId, sceneRuns]) => ({
      sceneId,
      runs: sceneRuns,
      latestTime: Math.max(...sceneRuns.map(r => r.start_time ? new Date(r.start_time).getTime() : 0)),
      hasLive: sceneRuns.some(r => r.run_id === currentRunId),
    }))
    .sort((a, b) => b.latestTime - a.latestTime)
}

// ── Components ──

interface Props {
  pastRuns: Run[]
  currentRunId: string
  serverReachable: boolean
  onEnter: (runId: string, sceneId?: string) => void
}

export default function PastRunsGrouped({ pastRuns, currentRunId, serverReachable, onEnter }: Props) {
  const { t } = useTranslation()
  const groups = useMemo(() => groupRuns(pastRuns, currentRunId), [pastRuns, currentRunId])

  if (!pastRuns.length) {
    return (
      <p className="text-xs text-muted-foreground py-1">
        {serverReachable ? t('lobby.noPastRuns') : t('lobby.serverUnreachable')}
      </p>
    )
  }

  const defaultOpen = groups
    .filter((g, i) => g.hasLive || i === 0)
    .map(g => g.sceneId)

  return (
    <Accordion type="multiple" defaultValue={defaultOpen}>
      {groups.map(group => (
        <RunGroup key={group.sceneId} group={group} currentRunId={currentRunId} onEnter={onEnter} />
      ))}
    </Accordion>
  )
}

function RunGroup({ group, currentRunId, onEnter }: {
  group: Group; currentRunId: string; onEnter: (runId: string, sceneId?: string) => void
}) {
  const { t } = useTranslation()
  const needsScroll = group.runs.length > MAX_VISIBLE
  const latestRelative = relativeTime(group.runs[0]?.start_time, t)

  const runList = (
    <div className="flex flex-col">
      {group.runs.map(run => (
        <RunRow key={run.run_id} run={run} isLive={run.run_id === currentRunId} onEnter={onEnter} />
      ))}
    </div>
  )

  return (
    <AccordionItem value={group.sceneId} className="last:border-b-0">
      {/* Group header: scene name (dominant) + last run time + count (subordinate) */}
      <AccordionTrigger className="py-3">
        <span className="flex flex-1 items-center gap-2 min-w-0">
          <span className="font-[family-name:var(--font-display)] text-[12px] font-semibold uppercase tracking-[1.5px] text-foreground truncate">
            {humanize(group.sceneId)}
          </span>
          <span className="font-mono text-[10px] text-muted-foreground/50 shrink-0">
            {group.runs.length}
          </span>
          <span className="ml-auto font-mono text-[10px] text-muted-foreground/40 shrink-0 mr-2">
            {latestRelative}
          </span>
        </span>
      </AccordionTrigger>

      <AccordionContent className="pb-2">
        {needsScroll ? (
          <ScrollArea className="h-[280px] pr-2">
            {runList}
          </ScrollArea>
        ) : runList}
      </AccordionContent>
    </AccordionItem>
  )
}

function RunRow({ run, isLive, onEnter }: {
  run: Run; isLive: boolean; onEnter: (runId: string, sceneId?: string) => void
}) {
  const { t } = useTranslation()
  const stats = runStats(run, t)

  return (
    <div
      onClick={() => onEnter(run.run_id, run.scene_id)}
      className={`flex items-baseline gap-3 py-[7px] px-2 cursor-pointer rounded-sm transition-colors hover:bg-muted/60 ${isLive ? 'bg-[var(--sage-dim)]' : ''}`}
    >
      {/* Time — primary scanning axis */}
      <span className="font-mono text-[11px] text-foreground w-[64px] shrink-0">
        {relativeTime(run.start_time, t)}
      </span>

      {/* Stats — secondary info */}
      <span className="font-mono text-[11px] text-muted-foreground/50 flex-1 truncate">
        {stats}
      </span>

      {/* Run ID — demoted, for debugging */}
      <span className="font-mono text-[10px] text-muted-foreground/30">
        {run.run_id.slice(0, 6)}
      </span>

      {/* Live — single indicator, subtle background does most of the work */}
      {isLive && (
        <span className="font-[family-name:var(--font-display)] text-[9px] font-semibold uppercase tracking-wider text-[var(--sage)]">
          {t('lobby.live')}
        </span>
      )}
    </div>
  )
}
