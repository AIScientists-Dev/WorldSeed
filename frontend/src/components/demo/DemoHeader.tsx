/* WorldSeed — Demo header: simplified top bar for demo mode.
 *
 * Includes: brand, world info, status, replay controls, gazette.
 * Excludes: run selector, gateway warning, agent controls, language switch,
 *           world controls, stop world.
 */

import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'
import { useWorldStore } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { useUIStore } from '@/stores/ui'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { BookOpen, Table } from '@phosphor-icons/react'
import GazettePopover from '@/components/gazette/GazettePopover'
import ReplayControls from '@/components/layout/ReplayControls'

export default function DemoHeader() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const tick = useWorldStore(s => s.tick)
  const replayActive = useReplayStore(s => s.active)
  const replayTick = useReplayStore(s => s.tick)
  const rightTab = useUIStore(s => s.rightTab)
  const toggleRightTab = useUIStore(s => s.toggleRightTab)

  return (
    <TooltipProvider delayDuration={300}>
      <header className="relative flex h-12 shrink-0 items-center border-b border-border/50 bg-void px-5">

        <div className="flex items-center gap-3">
          <span className="select-none font-[family-name:var(--font-display)] text-sm font-semibold tracking-[0.12em] text-foreground">
            WORLDSEED
          </span>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={() => navigate('/demo/intro')}>
                <BookOpen size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.worldInfo')}</TooltipContent>
          </Tooltip>
        </div>

        <div className="flex-1 min-w-4" />

        <span className="text-xs font-semibold whitespace-nowrap text-muted-foreground">
          {replayActive ? t('header.replay') : t('header.history')}
        </span>
        <span className="text-xs font-semibold tabular-nums text-muted-foreground ml-1.5">
          t{replayActive ? replayTick : tick}
        </span>

        <div className="flex-1 min-w-4" />

        <div className="flex items-center">
          <ReplayControls />
          <GazettePopover />

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label={t('header.dataInspector')}
                onClick={toggleRightTab}
                className={rightTab === 'inspector' ? 'bg-accent' : ''}
              >
                <Table size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.dataInspector')}</TooltipContent>
          </Tooltip>
        </div>
      </header>
    </TooltipProvider>
  )
}
