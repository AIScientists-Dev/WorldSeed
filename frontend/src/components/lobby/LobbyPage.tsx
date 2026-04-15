import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useLobbyStore } from '@/stores/lobby'
import { useWorldStore } from '@/stores/world'
import { apiPost, apiFetch } from '@/lib/api'
import { useNavigate } from 'react-router-dom'
import { NARRATOR_STYLES, narratorDescKey, buildNarratorPayload } from '@/lib/narrator'
import type { NarratorStyle } from '@/lib/narrator'
import { LS_NARRATOR_STYLE, LS_NARRATOR_PROMPT } from '@/lib/constants'
import LanguageSelect from '@/components/LanguageSelect'
import { Textarea } from '@/components/ui/textarea'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import DmModelSelect from './DmModelSelect'
import PastRunsGrouped from './PastRunsGrouped'

export default function LobbyPage() {
  const { t, i18n } = useTranslation()
  const configs = useLobbyStore(s => s.configs)
  const configPath = useLobbyStore(s => s.configPath)
  const dmModel = useLobbyStore(s => s.dmModel)
  const maxTicks = useLobbyStore(s => s.maxTicks)
  const timeoutMin = useLobbyStore(s => s.timeoutMin)
  const maxDmCalls = useLobbyStore(s => s.maxDmCalls)
  const tickInterval = useLobbyStore(s => s.tickInterval)
  const narratorStyle = useLobbyStore(s => s.narratorStyle)
  const narratorPrompt = useLobbyStore(s => s.narratorPrompt)
  const starting = useLobbyStore(s => s.starting)
  const error = useLobbyStore(s => s.error)
  const pastRuns = useLobbyStore(s => s.pastRuns)
  const serverReachable = useLobbyStore(s => s.serverReachable)
  const modelsLoaded = useLobbyStore(s => s.modelsLoaded)
  const availableModels = useLobbyStore(s => s.availableModels)
  const worldStatus = useWorldStore(s => s.worldStatus)
  const currentRunId = useWorldStore(s => s.currentRunId)
  const tick = useWorldStore(s => s.tick)
  const navigate = useNavigate()

  useEffect(() => {
    (async () => {
      const [cfgs, runs, health, models] = await Promise.all([
        apiFetch('/api/configs'),
        apiFetch('/api/past-runs'),
        apiFetch('/health'),
        apiFetch('/api/models'),
      ])
      if (cfgs) {
        useLobbyStore.setState({ configs: cfgs })
        if (!useLobbyStore.getState().configPath && cfgs.length) useLobbyStore.setState({ configPath: cfgs[0].path })
      }
      if (runs) useLobbyStore.setState({ pastRuns: runs })
      useLobbyStore.setState({ serverReachable: !!health })
      if (health) {
        useWorldStore.setState({
          worldStatus: health.status,
          tick: health.tick,
          systemAgents: health.system_agents || [],
        })
        if (health.run_id) {
          useWorldStore.getState().setCurrentRunId(health.run_id)
        } else {
          useWorldStore.setState({ currentRunId: '' })
        }
      }
      if (models) {
        const providers = models.providers || []
        const update: Record<string, any> = { availableModels: providers, modelsLoaded: true }
        if (!useLobbyStore.getState().dmModel) {
          update.dmModel = models.default || providers[0]?.models?.[0]?.id || ''
        }
        useLobbyStore.setState(update)
      }
    })()
  }, [])

  async function startWorld() {
    useLobbyStore.setState({ starting: true, error: '' })
    const ls = useLobbyStore.getState()
    const result = await apiPost('/api/world/start', {
      config_path: ls.configPath,
      dm_model: ls.dmModel,
      dm_fallback: ls.dmFallback,
      max_ticks: ls.maxTicks,
      timeout_min: ls.timeoutMin,
      max_dm_calls: ls.maxDmCalls,
      tick_interval: ls.tickInterval,
      language: i18n.language,
      ...buildNarratorPayload(ls.narratorStyle, ls.narratorPrompt),
    })
    if (result.ok) {
      if (result.data.run_id) useWorldStore.getState().setCurrentRunId(result.data.run_id)
      useLobbyStore.setState({ starting: false })
      navigate(`/run/${useWorldStore.getState().currentRunId}/intro`)
    } else {
      useLobbyStore.setState({
        error: result.data.detail || 'Failed to start world.',
        starting: false,
      })
    }
  }

  function enterDashboard(runId: string, sceneId?: string) {
    useWorldStore.setState({ viewingRunId: runId })
    if (sceneId) useWorldStore.setState({ scene: sceneId })
    navigate(`/run/${runId}/map`)
  }


  return (
    <div className="setup-page">
      <div className="absolute top-4 right-4">
        <LanguageSelect />
      </div>
      <div className="setup-brand">WORLD<em>SEED</em></div>
      <div className="setup-subtitle">{t('subtitle')}</div>

      <div className="setup-card">
        <div className="setup-card-title">{t('lobby.newWorld')}</div>
        <div className="setup-field">
          <label>{t('lobby.sceneConfig')}</label>
          <Select value={configPath} onValueChange={v => useLobbyStore.setState({ configPath: v })}>
            <SelectTrigger className="font-[family-name:var(--font-data)] text-[13px]">
              <SelectValue placeholder={t('lobby.selectConfig')} />
            </SelectTrigger>
            <SelectContent>
              {configs.map((c: any) => (
                <SelectItem key={c.path} value={c.path} className="font-[family-name:var(--font-data)] text-[13px]">
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="setup-field">
          <label>{t('lobby.narratorStyle')}</label>
          <Select value={narratorStyle} onValueChange={(v: string) => { useLobbyStore.setState({ narratorStyle: v as NarratorStyle }); localStorage.setItem(LS_NARRATOR_STYLE, v) }}>
            <SelectTrigger className="font-[family-name:var(--font-data)] text-[13px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {NARRATOR_STYLES.map(s => (
                <SelectItem key={s} value={s}>{t(`narrator.${s}`)}</SelectItem>
              ))}
              <SelectItem value="custom">{t('narrator.custom')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-[11px] text-[var(--ghost)] mt-1 pl-0.5 leading-snug font-[family-name:var(--font-data)]">
            {t(narratorDescKey(narratorStyle))}
          </p>
        </div>
        {narratorStyle === 'custom' && (
          <Textarea
            value={narratorPrompt}
            onChange={e => { useLobbyStore.setState({ narratorPrompt: e.target.value }); localStorage.setItem(LS_NARRATOR_PROMPT, e.target.value) }}
            placeholder={t('narrator.customPlaceholder')}
            rows={3}
            className="mb-3 text-xs leading-relaxed resize-y font-[family-name:var(--font-narrative)]"
          />
        )}
        <div className="setup-field-row">
          <div className="setup-field flex-[2]">
            <label>{t('lobby.dmModel')}</label>
            {modelsLoaded && availableModels.length === 0 ? (
              <div className="border border-[var(--rose)] rounded-md px-3 h-10 flex items-center text-[12px] text-[var(--rose)] font-[family-name:var(--font-data)]">
                {t('lobby.dmModelNone')}
              </div>
            ) : (
              <DmModelSelect />
            )}
          </div>
          <div className="setup-field">
            <label>{t('lobby.maxTicks')}</label>
            <Input type="number" value={maxTicks} onChange={e => useLobbyStore.setState({ maxTicks: Number(e.target.value) })} min={1} className="font-[family-name:var(--font-data)] text-[13px]" />
          </div>
        </div>
        <div className="setup-field-row">
          <div className="setup-field">
            <label>{t('lobby.tickInterval')}</label>
            <Input type="number" value={tickInterval} onChange={e => useLobbyStore.setState({ tickInterval: Number(e.target.value) })} min={0.1} step={0.1} className="font-[family-name:var(--font-data)] text-[13px]" />
          </div>
          <div className="setup-field">
            <label>{t('lobby.runDuration')}</label>
            <Input type="number" value={timeoutMin} onChange={e => useLobbyStore.setState({ timeoutMin: Number(e.target.value) })} min={1} className="font-[family-name:var(--font-data)] text-[13px]" />
          </div>
          <div className="setup-field">
            <label>{t('lobby.maxDmCalls')}</label>
            <Input type="number" value={maxDmCalls} onChange={e => useLobbyStore.setState({ maxDmCalls: Number(e.target.value) })} min={0} className="font-[family-name:var(--font-data)] text-[13px]" />
          </div>
        </div>
        <button className="setup-btn" onClick={startWorld} disabled={!configPath || !dmModel || starting}>
          {starting ? t('lobby.starting') : t('lobby.startWorld')}
        </button>
        {error && <div className="setup-error">{error}</div>}
      </div>

      {worldStatus !== 'lobby' && currentRunId && (
        <div className="setup-card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ cursor: 'pointer' }} onClick={() => enterDashboard(currentRunId)}>
              <div className="setup-card-title" style={{ color: 'var(--sage)', marginBottom: 4 }}>{'\u25B6'} {t('lobby.currentWorld')} {'\u2014'} {currentRunId.slice(0, 8)}</div>
              <div style={{ fontSize: 13, color: 'var(--ghost)' }}>
                {t(`header.${worldStatus}`, { defaultValue: worldStatus }).toUpperCase()} {'\u00B7'} Tick {tick} {'\u00B7'} {t('lobby.clickToEnter')}
              </div>
            </div>
            <button
              className="setup-btn"
              style={{ width: 'auto', marginTop: 0, padding: '8px 16px', fontSize: 11, color: 'var(--rose)', borderColor: 'var(--rose)', background: 'var(--rose-dim)' }}
              onClick={async () => {
                await apiPost('/api/world/stop', {})
                useWorldStore.setState({ worldStatus: 'lobby', currentRunId: '' })
                useLobbyStore.setState({ error: '' })
                const runs = await apiFetch('/api/past-runs')
                if (runs) useLobbyStore.setState({ pastRuns: runs })
              }}
            >
              {t('header.stopWorld')}
            </button>
          </div>
        </div>
      )}

      <div className="setup-card mt-4">
        <div className="setup-card-title">{t('lobby.pastRuns')}</div>
        <PastRunsGrouped
          pastRuns={pastRuns}
          currentRunId={currentRunId}
          serverReachable={serverReachable}
          onEnter={enterDashboard}
        />
      </div>
    </div>
  )
}
