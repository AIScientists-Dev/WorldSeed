/* WorldSeed — TheaterControlBar: auto-hide transport pill for theater mode.
 *
 * Top-center pill containing:
 *   - Scene + tick info
 *   - Transport controls (replay only): step back, play/pause, step forward
 *   - Scrubber + speed (replay only)
 *   - Replay toggle: start/stop replay
 *   - Close: exit theater
 *
 * Rendered by TheaterChrome only when theater is active + cursor is not idle.
 */

import { useTranslation } from 'react-i18next'
import { useWorldStore, selectEffectiveRunId } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { useTheaterStore } from '@/stores/theater'
import { useCommands } from '@/hooks/useCommands'
import {
  X, Play, Pause, SkipBack, SkipForward,
  ArrowCounterClockwise, Stop,
} from '@phosphor-icons/react'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4]

const btnClass = 'flex h-6 w-6 items-center justify-center rounded-full transition-colors'
const btnNormal = `${btnClass} text-white/60 hover:bg-white/15 hover:text-white/90`
const btnPrimary = `${btnClass} text-white/70 hover:bg-white/15 hover:text-white/95`

interface Props {
  onMouseEnter: () => void
  onMouseLeave: () => void
}

export default function TheaterControlBar({ onMouseEnter, onMouseLeave }: Props) {
  const { t } = useTranslation()
  const tick = useWorldStore(s => s.tick)
  const scene = useWorldStore(s => s.scene)
  const effectiveRunId = useWorldStore(selectEffectiveRunId)
  const replayActive = useReplayStore(s => s.active)
  const replayPaused = useReplayStore(s => s.paused)
  const replayTick = useReplayStore(s => s.tick)
  const replayTotal = useReplayStore(s => s.totalTicks)
  const replaySpeed = useReplayStore(s => s.speed)
  const { cmdResume, cmdPause } = useCommands()
  const running = useWorldStore(s => s.running)

  const isPlaying = replayActive ? !replayPaused : running
  const displayTick = replayActive ? replayTick : tick

  function togglePlay() {
    if (replayActive) {
      const rs = useReplayStore.getState()
      rs.paused ? rs.resume() : rs.pause()
    } else {
      running ? cmdPause() : cmdResume()
    }
  }

  function toggleReplay() {
    if (replayActive) {
      useReplayStore.getState().stop()
    } else {
      if (effectiveRunId) useReplayStore.getState().start(effectiveRunId)
    }
  }

  return (
    <TooltipProvider delayDuration={150}>
      <div
        className="flex items-center gap-1 rounded-full bg-black/40 backdrop-blur-lg border border-white/12 shadow-lg px-1.5 py-1 select-none"
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      >
        {/* Scene + tick */}
        <span className="px-2 font-mono text-[10px] text-white/60 tabular-nums">
          {scene && <>{scene} · </>}t{displayTick}{replayActive && <>/{replayTotal}</>}
        </span>

        <Sep />

        {/* Transport (replay only) */}
        {replayActive && (
          <>
            <Tip text={t('theater.stepBack')}>
              <button onClick={() => useReplayStore.getState().stepBack()} className={btnNormal}>
                <SkipBack size={12} weight="fill" />
              </button>
            </Tip>

            <Tip text={isPlaying ? t('theater.pause') : t('theater.play')}>
              <button onClick={togglePlay} className={btnPrimary}>
                {isPlaying ? <Pause size={14} weight="fill" /> : <Play size={14} weight="fill" />}
              </button>
            </Tip>

            <Tip text={t('theater.stepForward')}>
              <button onClick={() => useReplayStore.getState().stepForward()} className={btnNormal}>
                <SkipForward size={12} weight="fill" />
              </button>
            </Tip>
          </>
        )}

        {/* Scrubber + speed (replay) */}
        {replayActive && (
          <>
            <Sep />
            <Slider
              size="sm"
              className="w-24"
              min={0}
              max={replayTotal}
              step={1}
              value={[replayTick]}
              onValueChange={([v]) => useReplayStore.getState().seekTo(v)}
            />
            <Select value={String(replaySpeed)} onValueChange={v => useReplayStore.getState().setSpeed(Number(v))}>
              <SelectTrigger className="h-5 w-auto gap-0.5 border-0 bg-transparent px-1 font-mono text-[10px] text-white/60 shadow-none hover:text-white/90 [&>svg]:size-2.5 [&>svg]:opacity-40 [&>svg]:text-white/40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="center" className="min-w-0 z-[110]">
                {SPEEDS.map(s => (
                  <SelectItem key={s} value={String(s)} className="font-mono text-xs">{s}x</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        )}

        <Sep />

        {/* Replay toggle */}
        <Tip text={replayActive ? t('theater.stopReplay') : t('theater.replayThisRun')}>
          <button
            onClick={toggleReplay}
            className={replayActive
              ? 'flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium text-white/60 hover:bg-white/15 hover:text-white/90 transition-colors'
              : 'flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-semibold text-white/80 bg-white/10 hover:bg-white/20 hover:text-white transition-colors'
            }
          >
            {replayActive ? <Stop size={11} weight="fill" /> : <ArrowCounterClockwise size={13} />}
            {replayActive ? t('theater.stop') : t('theater.replay')}
          </button>
        </Tip>

        {/* Close theater */}
        <Tip text={t('theater.exitTheater')}>
          <button onClick={() => useTheaterStore.getState().exit()} className={btnNormal}>
            <X size={12} weight="bold" />
          </button>
        </Tip>
      </div>
    </TooltipProvider>
  )
}

/** Separator line between control groups. */
function Sep() {
  return <div className="h-3.5 w-px bg-white/15" />
}

/** Tooltip shorthand to reduce nesting boilerplate. */
function Tip({ text, children }: { text: string; children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent side="bottom" className="text-xs z-[110]">{text}</TooltipContent>
    </Tooltip>
  )
}
