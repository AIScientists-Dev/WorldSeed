/* ChronicleSheet — right-side slide-out panel for narrator chapters.
 *
 * Shows all chapters with collapsible cards, asides, whisper buttons.
 * Opening pauses the world. Closing resumes.
 * Step mode: auto-opens when chapter with asides appears.
 */

import { useState, useEffect, useMemo, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Separator } from '@/components/ui/separator'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { CaretRight } from '@phosphor-icons/react'
import { useUIStore } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { useStreamStore } from '@/stores/stream'
import { extractChapters } from '@/lib/chronicle'
import { apiPost } from '@/lib/api'
import { toast } from 'sonner'
import { cn } from '@/lib/utils'
import { useDemoStore } from '@/stores/demo'

export default function ChronicleSheet() {
  const { t } = useTranslation()
  const open = useUIStore(s => s.chronicleSheetOpen)
  const mode = useUIStore(s => s.chronicleMode)
  const worldStatus = useWorldStore(s => s.worldStatus)
  const streamRecords = useStreamStore(s => s.streamRecords)
  const isDemo = useDemoStore(s => s.active)
  const chapters = useMemo(() => extractChapters(streamRecords), [streamRecords])
  const [sentWhispers, setSentWhispers] = useState<Set<string>>(new Set())
  const prevChapterCount = useRef(-1)

  // Step mode: auto-open sheet when new chapter with asides appears.
  // ref starts at -1 so the first load seeds it without triggering.
  useEffect(() => {
    if (mode !== 'step' || chapters.length === 0) return
    if (prevChapterCount.current === -1) {
      // Initial load — seed baseline, don't trigger
      prevChapterCount.current = chapters.length
      return
    }
    if (chapters.length > prevChapterCount.current) {
      const latest = chapters[chapters.length - 1]
      if (latest.asides.length > 0) {
        apiPost('/api/tick/pause', {}).then(r => {
          if (r.ok) useWorldStore.setState({ worldStatus: 'paused' })
        })
        useUIStore.setState({ chronicleSheetOpen: true })
      }
    }
    prevChapterCount.current = chapters.length
  }, [chapters.length, mode])

  function handleOpenChange(isOpen: boolean) {
    useUIStore.setState({ chronicleSheetOpen: isOpen })
    if (isOpen && worldStatus === 'live') {
      // Opening sheet pauses
      apiPost('/api/tick/pause', {}).then(r => {
        if (r.ok) useWorldStore.setState({ worldStatus: 'paused' })
      })
    }
    if (!isOpen && worldStatus === 'paused') {
      // Closing sheet resumes
      apiPost('/api/tick/resume', {}).then(r => {
        if (r.ok) useWorldStore.setState({ worldStatus: 'live' })
      })
    }
  }

  return (
    <Sheet open={open} onOpenChange={handleOpenChange}>
      <SheetContent side="right" className="w-[45vw] min-w-[400px] max-w-[1500px] p-0 flex flex-col">
        <SheetHeader className="px-6 pt-6 pb-4 border-b border-border">
          <SheetTitle style={{ fontFamily: 'var(--font-narrative)' }} className="text-lg font-semibold">
            {t('chronicle.title', { defaultValue: 'Chronicle' })}
          </SheetTitle>
          <p className="text-[10px] text-muted-foreground uppercase tracking-wider mt-1" style={{ fontFamily: 'var(--font-data)' }}>
            {chapters.length} {t('chronicle.chapters', { defaultValue: 'chapters' })}
          </p>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-6 py-2">
            {chapters.map((ch, ci) => (
              <div key={ci}>
                <Collapsible defaultOpen={ci === chapters.length - 1}>
                  <CollapsibleTrigger className="w-full text-left group">
                    <div className="py-2.5 px-2 -mx-2 rounded-md hover:bg-muted/50 transition-colors">
                      <div className="flex items-center gap-2">
                        <CaretRight
                          size={10}
                          weight="bold"
                          className="shrink-0 text-muted-foreground/50 transition-transform group-data-[state=open]:rotate-90"
                        />
                        <span className="text-[10px] text-muted-foreground/60 tabular-nums tracking-wider uppercase" style={{ fontFamily: 'var(--font-data)' }}>
                          {t('chronicle.chapterMeta', { num: ch.num, tick: ch.tick })}
                        </span>
                      </div>
                      {/* 10px icon + 8px gap = 18px indent */}
                      <div className="ml-[18px] mt-0.5">
                        <div className="flex items-center justify-between gap-3">
                          <h3 className="text-[15px] font-semibold text-foreground leading-snug" style={{ fontFamily: 'var(--font-narrative)' }}>
                            {ch.title}
                          </h3>
                          {ch.asides.length > 0 && (
                            <span className="text-[10px] text-[var(--rose)]/60 shrink-0" style={{ fontFamily: 'var(--font-data)' }}>
                              {ch.asides.length} {t('chronicle.asides')}
                            </span>
                          )}
                        </div>
                        {ch.tldr && (
                          <p className="text-[13px] text-muted-foreground leading-relaxed mt-0.5 line-clamp-2 group-data-[state=open]:line-clamp-none" style={{ fontFamily: 'var(--font-narrative)' }}>
                            {ch.tldr}
                          </p>
                        )}
                      </div>
                    </div>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <div className="ml-[18px] mt-2 pb-4">
                      <div className="text-[13px] text-[var(--slate)] leading-relaxed whitespace-pre-line" style={{ fontFamily: 'var(--font-narrative)' }}>
                        {ch.paragraphs.join('\n\n').replace(/^[—–-]\s*/gm, '• ')}
                      </div>

                      {ch.asides.length > 0 && (
                        <div className="mt-6 space-y-3">
                          <p className="text-[10px] uppercase tracking-wider text-[var(--rose)]" style={{ fontFamily: 'var(--font-data)' }}>
                            {t('chronicle.asidesLabel')}
                          </p>
                          {ch.asides.map((aside, ii) => (
                            <div key={ii} className="space-y-1.5">
                              <p className="border-l border-[var(--rose)]/25 pl-3 text-[13px] text-foreground/80 leading-relaxed" style={{ fontFamily: 'var(--font-narrative)' }}>
                                {aside.text}
                              </p>
                              {aside.whispers.length > 0 && (
                                <div className="pl-3 flex flex-col gap-1.5">
                                  {aside.whispers.map((w, wi) => {
                                    const key = `${ch.tick}:${ii}:${wi}`
                                    const sent = sentWhispers.has(key)
                                    return (
                                      <button
                                        key={wi}
                                        disabled={sent || isDemo}
                                        className={cn(
                                          'w-full text-left text-[12px] px-3 py-1 rounded-md border transition-all',
                                          sent || isDemo
                                            ? 'border-[var(--sage)]/40 text-[var(--sage)] opacity-70'
                                            : 'border-[var(--amber)]/30 text-[var(--amber)] hover:border-[var(--amber)]/60 hover:bg-[var(--amber)]/5 cursor-pointer',
                                        )}
                                        onClick={async () => {
                                          if (isDemo) return
                                          const r = await apiPost('/api/whisper', { agent_id: w.target, message: w.label })
                                          if (r.ok) {
                                            setSentWhispers(prev => new Set(prev).add(key))
                                            toast.success(t('chronicle.whisperSent', { agent: w.target }))
                                          } else {
                                            toast.error(r.data?.detail || t('chronicle.whisperFailed'))
                                          }
                                        }}
                                      >
                                        {sent ? t('chronicle.whisperDone', { agent: w.target, note: w.label }) : t('chronicle.whisperAction', { agent: w.target, note: w.label })}
                                      </button>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </CollapsibleContent>
                </Collapsible>
                {ci < chapters.length - 1 && <Separator className="my-2" />}
              </div>
            ))}
            {chapters.length === 0 && (
              <p className="text-[12px] text-muted-foreground italic" style={{ fontFamily: 'var(--font-narrative)' }}>
                {t('chronicle.awaiting', { defaultValue: 'Awaiting first chapter...' })}
              </p>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  )
}
