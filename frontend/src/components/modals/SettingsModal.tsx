import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { useLobbyStore } from '@/stores/lobby'
import { useCommands } from '@/hooks/useCommands'
import { apiPatch, apiPost } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'
import { Slider } from '@/components/ui/slider'
import { Badge } from '@/components/ui/badge'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { Circle, Timer, Robot, GearSix, Warning, Broadcast, ChartBar, CaretDown, BookOpen } from '@phosphor-icons/react'
import DmModelSelect from '@/components/lobby/DmModelSelect'
import { NARRATOR_STYLES, narratorDescKey, buildNarratorPayload } from '@/lib/narrator'
import type { NarratorStyle } from '@/lib/narrator'
import { LS_NARRATOR_STYLE } from '@/lib/constants'

export default function SettingsModal() {
  const { t } = useTranslation()
  const showSettings = useUIStore(s => s.showSettings)
  const speed = useUIStore(s => s.speed)
  const worldStatus = useWorldStore(s => s.worldStatus)
  const viewingRunId = useWorldStore(s => s.viewingRunId)
  const currentRunId = useWorldStore(s => s.currentRunId)
  const gatewayConnected = useWorldStore(s => s.gatewayStatus.connected)
  const tokenCount = useWorldStore(s => s.tokenCount)
  const narratorStyle = useWorldStore(s => s.narratorStyle)
  const configs = useLobbyStore(s => s.configs)
  const availableModels = useLobbyStore(s => s.availableModels)
  const { cmdStop, cmdGatewayRestart, onSpeedChange } = useCommands()

  const isLive = worldStatus !== 'lobby' && viewingRunId === currentRunId

  const [tickInterval, setTickInterval] = useState(5)
  const [maxTicks, setMaxTicks] = useState(200)
  const [timeoutMin, setTimeoutMin] = useState(10)
  const [maxDmCalls, setMaxDmCalls] = useState(50)
  const [configPath, setConfigPath] = useState('')
  const [dangerOpen, setDangerOpen] = useState(false)

  async function applySettings() {
    await apiPatch('/api/settings', {
      tick_interval: tickInterval,
      max_ticks: maxTicks,
      timeout_min: timeoutMin,
      max_dm_calls: maxDmCalls,
    })
    useUIStore.setState({ showSettings: false })
  }

  async function updateModel() {
    await apiPatch('/api/settings', {
      dm_model: useLobbyStore.getState().dmModel,
    })
    useUIStore.setState({ showSettings: false })
  }

  async function reloadConfig() {
    if (!configPath) return
    const result = await apiPost('/api/config/reload', { config_path: configPath })
    if (result.ok) {
      useUIStore.setState({ showSettings: false })
      window.location.reload()
    }
  }

  function handleSpeedChange(val: number[]) {
    const syntheticEvent = { target: { value: String(val[0]) } }
    onSpeedChange(syntheticEvent as any)
  }

  return (
    <Dialog open={showSettings} onOpenChange={(open) => useUIStore.setState({ showSettings: open })}>
      <DialogContent className="sm:max-w-lg gap-0 p-0">
        <DialogHeader className="px-5 pt-5 pb-0">
          <DialogTitle className="text-base">{t('settings.title')}</DialogTitle>
          <DialogDescription className="text-xs">{t('settings.description')}</DialogDescription>
        </DialogHeader>

        <div className="max-h-[70vh] overflow-y-auto px-5 pb-5">

          {/* ── Tick Control ── */}
          <div className="mt-4">
            <div className="mb-3 flex items-center gap-2 text-muted-foreground">
              <Timer size={14} />
              <span className="text-xs font-medium">{t('settings.tickControl')}</span>
            </div>
            <div className="rounded-lg border border-border/60 bg-muted/20 p-3">
              <div className="grid grid-cols-2 gap-2.5">
                <div className="space-y-1">
                  <Label htmlFor="tick-interval" className="text-[11px] text-muted-foreground">{t('settings.interval')}</Label>
                  <Input id="tick-interval" type="number" value={tickInterval} onChange={e => setTickInterval(Number(e.target.value))} min={0.1} step={0.1} className="h-7 font-mono text-xs" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="max-ticks" className="text-[11px] text-muted-foreground">{t('settings.maxTicks')}</Label>
                  <Input id="max-ticks" type="number" value={maxTicks} onChange={e => setMaxTicks(Number(e.target.value))} min={1} className="h-7 font-mono text-xs" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="run-duration" className="text-[11px] text-muted-foreground">{t('settings.duration')}</Label>
                  <Input id="run-duration" type="number" value={timeoutMin} onChange={e => setTimeoutMin(Number(e.target.value))} min={1} className="h-7 font-mono text-xs" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="max-dm" className="text-[11px] text-muted-foreground">{t('settings.maxDmCalls')}</Label>
                  <Input id="max-dm" type="number" value={maxDmCalls} onChange={e => setMaxDmCalls(Number(e.target.value))} min={0} className="h-7 font-mono text-xs" />
                </div>
              </div>

              {isLive && (
                <div className="mt-3 border-t border-border/40 pt-3">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-muted-foreground">{t('settings.speed')}</span>
                    <Badge variant="outline" className="h-4 px-1.5 font-mono text-[10px] tabular-nums">{speed.toFixed(1)}x</Badge>
                  </div>
                  <Slider
                    value={[speed]}
                    min={0.1}
                    max={5}
                    step={0.1}
                    onValueChange={handleSpeedChange}
                    className="mt-2"
                  />
                </div>
              )}
            </div>
            <Button size="sm" onClick={applySettings} className="mt-2.5 w-full">{t('settings.apply')}</Button>
          </div>

          <Separator className="my-4" />

          {/* ── DM Model ── */}
          {availableModels.length > 0 && (
            <div>
              <div className="mb-3 flex items-center gap-2 text-muted-foreground">
                <Robot size={14} />
                <span className="text-xs font-medium">{t('settings.dmModel')}</span>
              </div>
              <div className="space-y-2.5">
                <DmModelSelect compact triggerClassName="h-7" />
                <Button size="sm" variant="outline" onClick={updateModel} className="w-full">{t('settings.updateModel')}</Button>
              </div>
            </div>
          )}

          {/* ── Narrator Style ── */}
          {isLive && (
            <>
              <Separator className="my-4" />
              <div>
                <div className="mb-3 flex items-center gap-2 text-muted-foreground">
                  <BookOpen size={14} />
                  <span className="text-xs font-medium">{t('settings.narratorStyle')}</span>
                </div>
                <div className="space-y-2.5">
                  <Select
                    value={narratorStyle}
                    onValueChange={(v) => {
                      const style = v as NarratorStyle
                      useWorldStore.setState({ narratorStyle: style })
                      localStorage.setItem(LS_NARRATOR_STYLE, style)
                      apiPatch('/api/settings', buildNarratorPayload(style, style === 'custom' ? useWorldStore.getState().narratorPrompt : ''))
                    }}
                  >
                    <SelectTrigger className="h-7 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {NARRATOR_STYLES.map(s => (
                        <SelectItem key={s} value={s} className="text-xs">{t(`narrator.${s}`)}</SelectItem>
                      ))}
                      <SelectItem value="custom" className="text-xs">{t('narrator.custom')}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-[10px] text-muted-foreground leading-snug font-[family-name:var(--font-data)]">
                    {t(narratorDescKey(narratorStyle))}
                  </p>
                </div>
              </div>
            </>
          )}

          {/* ── Gateway ── */}
          {isLive && (
            <>
              <Separator className="my-4" />
              <div>
                <div className="mb-3 flex items-center gap-2 text-muted-foreground">
                  <Broadcast size={14} />
                  <span className="text-xs font-medium">{t('settings.gateway')}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
                  <div className="flex items-center gap-2">
                    <Circle size={8} className={`fill-current ${gatewayConnected ? 'text-emerald-500/70' : 'text-muted-foreground/30'}`} />
                    <span className="text-xs">{gatewayConnected ? t('settings.connected') : t('settings.disconnected')}</span>
                  </div>
                  <Button size="xs" variant="outline" onClick={() => cmdGatewayRestart()}>{t('settings.restart')}</Button>
                </div>
              </div>
            </>
          )}

          {/* ── Stats ── */}
          {tokenCount > 0 && (
            <>
              <Separator className="my-4" />
              <div>
                <div className="mb-3 flex items-center gap-2 text-muted-foreground">
                  <ChartBar size={14} />
                  <span className="text-xs font-medium">{t('settings.stats')}</span>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border/60 bg-muted/20 px-3 py-2">
                  <span className="text-xs text-muted-foreground">{t('settings.totalTokens')}</span>
                  <span className="font-mono text-xs font-semibold tabular-nums">{tokenCount.toLocaleString()}</span>
                </div>
              </div>
            </>
          )}

          <Separator className="my-4" />

          {/* ── Config Switch ── */}
          <div>
            <div className="mb-3 flex items-center gap-2 text-muted-foreground">
              <GearSix size={14} />
              <span className="text-xs font-medium">{t('settings.configSwitch')}</span>
            </div>
            <div className="space-y-2.5">
              <Select value={configPath} onValueChange={setConfigPath}>
                <SelectTrigger className="h-7 w-full text-xs">
                  <SelectValue placeholder={t('lobby.selectConfig')} />
                </SelectTrigger>
                <SelectContent>
                  {configs.map((c: any) => (
                    <SelectItem key={c.path} value={c.path}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" onClick={reloadConfig} className="w-full">{t('settings.reloadConfig')}</Button>
            </div>
          </div>

          <Separator className="my-4" />

          {/* ── Danger Zone (collapsible) ── */}
          <Collapsible open={dangerOpen} onOpenChange={setDangerOpen}>
            <CollapsibleTrigger className="flex w-full items-center gap-2 text-muted-foreground/60 hover:text-destructive transition-colors">
              <Warning size={14} />
              <span className="text-xs font-medium">{t('settings.dangerZone')}</span>
              <CaretDown size={12} className={`ml-auto transition-transform ${dangerOpen ? 'rotate-180' : ''}`} />
            </CollapsibleTrigger>
            <CollapsibleContent>
              <div className="mt-2.5 rounded-lg border border-destructive/20 bg-destructive/5 p-3">
                <p className="mb-2.5 text-[11px] leading-relaxed text-muted-foreground">
                  {t('settings.dangerWarning')}
                </p>
                <Button variant="destructive" size="sm" onClick={cmdStop} className="w-full">{t('settings.stopWorld')}</Button>
              </div>
            </CollapsibleContent>
          </Collapsible>
        </div>
      </DialogContent>
    </Dialog>
  )
}
