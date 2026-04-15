/* WorldSeed — Replay controls: start button + expanded playback bar.
 *
 * Shared between HeaderBar (product) and DemoHeader (demo).
 * Reads all state from replay store — no props needed.
 */

import { useTranslation } from 'react-i18next'
import { useWorldStore, selectEffectiveRunId } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Play, Pause, SkipForward, SkipBack, ArrowCounterClockwise, X } from '@phosphor-icons/react'

export default function ReplayControls() {
  const { t } = useTranslation()
  const effectiveRunId = useWorldStore(selectEffectiveRunId)
  const replayActive = useReplayStore(s => s.active)
  const replayPaused = useReplayStore(s => s.paused)
  const replayTick = useReplayStore(s => s.tick)
  const replayTotal = useReplayStore(s => s.totalTicks)
  const replaySpeed = useReplayStore(s => s.speed)

  if (!replayActive && !effectiveRunId) return null

  return (
    <div className="flex items-center gap-0.5 mr-2 rounded-md bg-secondary/50 px-1 py-0.5">
      {replayActive ? (
        <>
          <span className="px-1.5 font-[family-name:var(--font-display)] text-xs font-semibold text-muted-foreground select-none">
            {t('header.replay')}
          </span>
          <div className="h-3.5 w-px bg-border/50" />
          <Button variant="ghost" size="icon-sm" onClick={() => useReplayStore.getState().stepBack()}>
            <SkipBack size={14} />
          </Button>
          <Button variant="ghost" size="icon-sm" className="bg-secondary" onClick={() => {
            const rs = useReplayStore.getState()
            rs.paused ? rs.resume() : rs.pause()
          }}>
            {replayPaused ? <Play size={14} weight="fill" /> : <Pause size={14} />}
          </Button>
          <Button variant="ghost" size="icon-sm" onClick={() => useReplayStore.getState().stepForward()}>
            <SkipForward size={14} />
          </Button>
          <div className="mx-1 h-4 w-px bg-border/50" />
          <Slider
            size="sm"
            className="w-28"
            min={0}
            max={replayTotal}
            step={1}
            value={[replayTick]}
            onValueChange={([v]) => useReplayStore.getState().seekTo(v)}
          />
          <span className="px-1 font-[family-name:var(--font-data)] text-xs tabular-nums text-muted-foreground">
            {replayTick}/{replayTotal}
          </span>
          <Select value={String(replaySpeed)} onValueChange={v => useReplayStore.getState().setSpeed(Number(v))}>
            <SelectTrigger className="h-6 w-auto gap-0.5 border-0 bg-transparent px-1 font-[family-name:var(--font-data)] text-xs text-muted-foreground shadow-none [&>svg]:size-2.5 [&>svg]:opacity-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent align="end" className="min-w-0">
              {[0.5, 0.75, 1, 1.25, 1.5, 2, 3].map(s => (
                <SelectItem key={s} value={String(s)} className="font-[family-name:var(--font-data)] text-xs">{s}x</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="mx-0.5 h-4 w-px bg-border/50" />
          <Button variant="ghost" size="xs" className="hover:text-destructive" onClick={() => useReplayStore.getState().stop()}>
            <X size={12} />
            {t('header.stopReplay')}
          </Button>
        </>
      ) : (
        <Button variant="ghost" size="xs" onClick={() => {
          if (effectiveRunId) useReplayStore.getState().start(effectiveRunId)
        }}>
          <ArrowCounterClockwise size={12} />
          {t('header.replay')}
        </Button>
      )}
    </div>
  )
}
