/* WorldSeed — GmPill: floating GM action bar (bottom-center of map).
 *
 * Collapsed: [✨ Command | 💬 Whisper]
 * Expanded:  [✨ Command | 💬] [input...] [↑]    (active keeps label, inactive icon only)
 * Switch:    [✨ | 💬 Whisper] [agent ▾] [input...] [↑]
 *
 * Esc to collapse. No close button — Esc is enough.
 * Hidden in theater mode.
 */

import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { PAPER_EASE } from '@/lib/motion'
import { motion } from 'motion/react'
import { useTheaterStore } from '@/stores/theater'
import { useWorldStore } from '@/stores/world'
import { useMapSelection } from '@/components/MapSelectionContext'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { MagicWand, ChatCircle } from '@phosphor-icons/react'
import GmPillCommand from './GmPillCommand'
import GmPillWhisper from './GmPillWhisper'

type Mode = 'command' | 'whisper' | null // null = collapsed


export default function GmPill() {
  const { t } = useTranslation()
  const theaterActive = useTheaterStore(s => s.active)
  const worldStatus = useWorldStore(s => s.worldStatus)
  const viewingRunId = useWorldStore(s => s.viewingRunId)
  const { selectedId } = useMapSelection()

  const [mode, setMode] = useState<Mode>(null)

  const collapse = useCallback(() => setMode(null), [])

  useEffect(() => {
    if (!mode) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') collapse() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [mode, collapse])

  if (theaterActive || (worldStatus === 'lobby' && !viewingRunId)) return null

  const open = mode !== null

  return (
    <div className="absolute bottom-4 right-4 z-40">
      <motion.div
        layout
        transition={{ duration: 0.22, ease: PAPER_EASE }}
        className={`flex items-center gap-px rounded-xl border border-border/50 bg-white/88 shadow-sm backdrop-blur-lg ${open ? 'w-[420px] px-1.5 py-1' : 'px-1 py-1'}`}
      >
        <TooltipProvider delayDuration={300}>
          <Tab mode="command" icon={<MagicWand size={13} />} label={t('gm.command')} tooltip={t('gm.commandTooltip')}
            active={mode === 'command'} open={open} onClick={() => setMode('command')} />
          {!open && <div className="mx-px h-3.5 w-px bg-border/50" />}
          <Tab mode="whisper" icon={<ChatCircle size={13} />} label={t('gm.whisper')} tooltip={t('gm.whisperTooltip')}
            active={mode === 'whisper'} open={open} onClick={() => setMode('whisper')} />
        </TooltipProvider>

        {/* Input area — only when open */}
        {open && (
          <div className="ml-1 flex min-w-0 flex-1 items-center gap-1.5">
            {mode === 'command' && <GmPillCommand />}
            {mode === 'whisper' && <GmPillWhisper preSelectedAgentId={selectedId} />}
          </div>
        )}
      </motion.div>
    </div>
  )
}

function Tab({ icon, label, tooltip, active, open, onClick }: {
  mode: string; icon: React.ReactNode; label: string; tooltip: string
  active: boolean; open: boolean; onClick: () => void
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          onClick={onClick}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
            active ? 'bg-secondary/60 text-foreground' : 'text-muted-foreground hover:bg-accent hover:text-foreground'
          } ${open && !active ? '!px-2' : ''}`}
        >
          {icon}
          {(!open || active) && <span>{label}</span>}
        </button>
      </TooltipTrigger>
      {!open && <TooltipContent side="left" collisionPadding={8}>{tooltip}</TooltipContent>}
    </Tooltip>
  )
}
