/* ChronicleBar — persistent horizontal bar below the header.
 *
 * Shows the latest narrator chapter: Ch.N + title + tldr + ironies count.
 * Persists until the next chapter replaces it.
 * Click opens ChronicleSheet.
 * Pulse animation when a new chapter with ironies arrives (step mode).
 *
 * Chronicle mode toggle: shared component used in both awaiting and active states.
 */

import { useMemo, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretRight, Infinity, BookmarkSimple } from '@phosphor-icons/react'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { useStreamStore } from '@/stores/stream'
import { useUIStore, type ChronicleMode } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { apiPost } from '@/lib/api'
import { extractLatestChapter } from '@/lib/chronicle'

/* ── Reusable mode toggle ── */

function ModeToggle() {
  const { t } = useTranslation()
  const chronicleMode = useUIStore(s => s.chronicleMode)

  function select(m: ChronicleMode) {
    localStorage.setItem('ws-chronicle-mode', m)
    useUIStore.setState({ chronicleMode: m })
  }

  const modes = [
    { key: 'auto' as const, Icon: Infinity, tip: t('header.chronicleAutoTip') },
    { key: 'step' as const, Icon: BookmarkSimple, tip: t('header.chronicleStepTip') },
  ]

  return (
    <TooltipProvider delayDuration={300}>
      <div
        className="flex shrink-0 items-center gap-0.5"
        onClick={(e) => e.stopPropagation()}
      >
        {modes.map(({ key, Icon, tip }) => {
          const active = chronicleMode === key
          return (
            <Tooltip key={key}>
              <TooltipTrigger asChild>
                <button
                  onClick={() => select(key)}
                  className={`p-1.5 rounded-full transition-all duration-200 ${
                    active
                      ? 'text-foreground bg-foreground/8'
                      : 'text-muted-foreground/35 hover:text-muted-foreground hover:bg-muted/20'
                  }`}
                >
                  <Icon size={15} weight={active ? 'bold' : 'regular'} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="bottom" className="text-xs">
                {tip}
              </TooltipContent>
            </Tooltip>
          )
        })}
      </div>
    </TooltipProvider>
  )
}

/* ── Main bar ── */

export default function ChronicleBar() {
  const { t } = useTranslation()
  const streamRecords = useStreamStore(s => s.streamRecords)
  const chronicleMode = useUIStore(s => s.chronicleMode)
  const replayActive = useReplayStore(s => s.active)
  const replayTick = useReplayStore(s => s.tick)
  const maxTick = replayActive ? replayTick : undefined
  const chapter = useMemo(() => extractLatestChapter(streamRecords, maxTick), [streamRecords, maxTick])
  const [flash, setFlash] = useState(false)
  const prevNum = useRef(0)

  // Flash when new chapter arrives
  useEffect(() => {
    if (!chapter || chapter.num === prevNum.current) return
    prevNum.current = chapter.num
    setFlash(true)
    const t = setTimeout(() => setFlash(false), 1500)
    return () => clearTimeout(t)
  }, [chapter?.num])

  /* Awaiting state — no chapter yet */
  if (!chapter) {
    return (
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-border">
        <span className="text-[12px] text-muted-foreground italic" style={{ fontFamily: 'var(--font-narrative)' }}>
          {t('chronicle.awaiting')}
        </span>
        <ModeToggle />
      </div>
    )
  }

  /* Active state — showing chapter */
  const hasAsides = chapter.asides.length > 0
  const waiting = chronicleMode === 'step' && hasAsides && flash

  return (
    <div
           onClick={() => {
        useUIStore.setState({ chronicleSheetOpen: true })
        apiPost('/api/tick/pause', {}).then(r => {
          if (r.ok) useWorldStore.setState({ worldStatus: 'paused' })
        })
      }}
      className={`px-4 py-2.5 border-b cursor-pointer transition-all ${
        waiting
          ? 'border-[var(--amber)] bg-[var(--amber)]/5 animate-pulse'
          : flash
            ? 'border-[var(--amber)] bg-[var(--amber)]/5'
            : 'border-border hover:bg-muted/30'
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="text-[10px] text-muted-foreground shrink-0 tabular-nums" style={{ fontFamily: 'var(--font-data)' }}>
          {t('chronicle.chapterNum', { num: chapter.num })}
        </span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-foreground leading-tight truncate" style={{ fontFamily: 'var(--font-narrative)' }}>
            {chapter.title}
          </div>
          <div className="text-[12px] text-muted-foreground leading-tight truncate mt-0.5" style={{ fontFamily: 'var(--font-narrative)' }}>
            {chapter.tldr.replace(/^[—–-]\s*/, '• ')}
          </div>
        </div>
        {hasAsides && (
          <span className="text-[10px] text-[var(--rose)] shrink-0" style={{ fontFamily: 'var(--font-data)' }}>
            {chapter.asides.length} {t('chronicle.asides')}
          </span>
        )}
        <ModeToggle />
        <CaretRight size={14} weight="bold" className="text-muted-foreground shrink-0" />
      </div>
    </div>
  )
}
