import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useWorldStore, selectIsViewingHistory, selectEffectiveRunId } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { useUIStore } from '@/stores/ui'
import { useCommands } from '@/hooks/useCommands'
import { useNavigate } from 'react-router-dom'

import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import LanguageSelect from '@/components/LanguageSelect'
import ReplayControls from '@/components/layout/ReplayControls'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import {
  ArrowLeft, Play, Pause, SkipForward, Plug, GearSix, Stop,
  BellRinging, Table, BookOpen, Faders, X,
} from '@phosphor-icons/react'
import GazettePopover from '@/components/gazette/GazettePopover'


export default function HeaderBar() {
  const { t } = useTranslation()
  const worldStatus = useWorldStore(s => s.worldStatus)
  const currentRunId = useWorldStore(s => s.currentRunId)
  const isViewingHistory = useWorldStore(selectIsViewingHistory)
  const effectiveRunId = useWorldStore(selectEffectiveRunId)
  const pastRunsList = useWorldStore(s => s.pastRunsList)
  const replayActive = useReplayStore(s => s.active)
  const rightTab = useUIStore(s => s.rightTab)
  const toggleRightTab = useUIStore(s => s.toggleRightTab)

  const navigate = useNavigate()

  const healthChecked = useWorldStore(s => s.healthChecked)
  const gatewayConnected = useWorldStore(s => s.gatewayStatus.connected)
  const agentsInfo = useWorldStore(s => s.agentsInfo)

  const {
    cmdPause, cmdResume, cmdStep, cmdStop,
    cmdConnectAgents,
  } = useCommands()


  const [worldExpanded, setWorldExpanded] = useState(false)

  const statusLabel = replayActive ? t('header.replay')
    : isViewingHistory ? t('header.history')
    : worldStatus === 'live' ? t('header.live')
    : worldStatus === 'paused' ? t('header.paused')
    : worldStatus === 'ready' ? t('header.ready')
    : t('header.lobby')

  const currentRunValue = effectiveRunId || ''

  function goLobby() {
    useReplayStore.getState().stop()
    useWorldStore.setState({ viewingRunId: '' })
    navigate('/lobby')
  }

  function switchRun(runId: string) {
    useReplayStore.getState().stop()
    useWorldStore.setState({ viewingRunId: runId })
    navigate(`/run/${runId}/map`)
  }

  return (
    <TooltipProvider delayDuration={300}>
      <header className="relative flex h-12 shrink-0 items-center border-b border-border/50 bg-void px-3">

        <div className="flex items-center gap-3">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={goLobby}>
                <ArrowLeft size={16} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.backToLobby')}</TooltipContent>
          </Tooltip>

          <span className="select-none font-[family-name:var(--font-display)] text-sm font-semibold tracking-[0.12em] text-foreground">
            WORLDSEED
          </span>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="icon-sm" onClick={() => {
                if (effectiveRunId) navigate(`/run/${effectiveRunId}/intro`)
              }}>
                <BookOpen size={14} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.worldInfo')}</TooltipContent>
          </Tooltip>
        </div>

        <div className="ml-4 text-xs leading-7">
          <Select value={currentRunValue} onValueChange={switchRun}>
            <SelectTrigger className="h-7 w-auto gap-1 border-none bg-transparent px-2 py-0 text-xs font-normal leading-7 text-foreground/70 shadow-none hover:text-foreground [&>svg]:ml-1 [&>svg]:size-3.5 [&>svg]:shrink-0 [&>svg]:opacity-40">
              <SelectValue placeholder={t('header.noRun')} />
            </SelectTrigger>
            <SelectContent align="start" className="max-h-[300px]">
              {currentRunId && (
                <SelectItem value={currentRunId} className="text-xs">
                  <span className="text-muted-foreground">{currentRunId.slice(0, 8)}</span>
                </SelectItem>
              )}
              {pastRunsList.map((r: any) =>
                r.run_id !== currentRunId ? (
                  <SelectItem key={r.run_id} value={r.run_id} className="text-xs">
                    <span className="text-muted-foreground">{r.run_id.slice(0, 8)}</span> · {r.scene_id}{r.tick_count ? ` · ${r.tick_count}t` : ''}
                  </SelectItem>
                ) : null
              )}
            </SelectContent>
          </Select>
        </div>

        <div className="flex-1 min-w-4" />

        <span className="text-xs font-semibold whitespace-nowrap text-muted-foreground">
          {statusLabel}
        </span>
        <span className="text-xs font-semibold tabular-nums text-muted-foreground ml-1.5">
          <TickCounter />
        </span>

        <div className="flex-1 min-w-4" />

        <div className="flex items-center">
          {healthChecked && !gatewayConnected && (
            <Tooltip>
              <TooltipTrigger asChild>
                <span className="inline-flex items-center gap-1 mr-2 text-xs font-medium text-destructive font-[family-name:var(--font-display)]">
                  <Plug size={12} />
                  {t('settings.disconnected')}
                </span>
              </TooltipTrigger>
              <TooltipContent>{t('header.gatewayDisconnected')}</TooltipContent>
            </Tooltip>
          )}

          {/* ── World Control: collapsed = button, expanded = label + controls ── */}
          {!isViewingHistory && !replayActive && worldStatus !== 'lobby' && (
            <div className="flex items-center gap-0.5 mr-2 rounded-md bg-secondary/50 px-1 py-0.5">
              {worldExpanded ? (
                <>
                  {(worldStatus === 'ready' || worldStatus === 'paused') && (
                    <Button variant="ghost" size="xs" onClick={() => cmdResume()}>
                      <Play size={12} weight="fill" />
                      {worldStatus === 'ready' ? t('header.play') : t('header.resume')}
                    </Button>
                  )}
                  {worldStatus === 'live' && (
                    <Button variant="ghost" size="xs" onClick={() => cmdPause()}>
                      <Pause size={12} />
                      {t('header.pause')}
                    </Button>
                  )}
                  {(worldStatus === 'live' || worldStatus === 'paused') && (
                    <Button variant="ghost" size="xs" onClick={() => cmdStep()}>
                      <SkipForward size={12} />
                      {t('header.step')}
                    </Button>
                  )}
                  <div className="mx-0.5 h-4 w-px bg-border/50" />
                  <Button variant="ghost" size="xs" onClick={() => setWorldExpanded(false)}>
                    <X size={12} />
                  </Button>
                </>
              ) : (
                <Button variant="ghost" size="xs" onClick={() => setWorldExpanded(true)}>
                  <Faders size={12} />
                  {t('header.worldControls')}
                </Button>
              )}
            </div>
          )}

          <ReplayControls />

          <GazettePopover />

          {agentsInfo.total > 0 && agentsInfo.pending.length > 0 && (
            <span className="text-xs font-semibold tabular-nums text-muted-foreground font-[family-name:var(--font-data)] mr-1">
              {agentsInfo.ready.length}/{agentsInfo.total}
            </span>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <Button variant="ghost" size="xs" onClick={() => cmdConnectAgents()}>
                <BellRinging size={12} />
                {t('header.wakeAll')}
              </Button>
            </TooltipTrigger>
            <TooltipContent>{t('header.wakeAllTooltip')}</TooltipContent>
          </Tooltip>

          <div className="flex items-center gap-1">
            <LanguageSelect />

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

            <Tooltip>
              <TooltipTrigger asChild>
                <Button variant="ghost" size="icon-sm" aria-label={t('header.settings')} onClick={() => useUIStore.setState({ showSettings: true })}>
                  <GearSix size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('header.settings')}</TooltipContent>
            </Tooltip>

            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                  onClick={cmdStop}
                >
                  <Stop size={14} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>{t('header.stopWorld')}</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </header>

    </TooltipProvider>
  )
}

function TickCounter() {
  const tick = useWorldStore(s => s.tick)
  const replayActive = useReplayStore(s => s.active)
  const replayTick = useReplayStore(s => s.tick)
  return <span className="text-xs font-semibold tabular-nums text-muted-foreground ml-1.5">t{replayActive ? replayTick : tick}</span>
}
