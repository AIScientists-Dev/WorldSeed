/* WorldSeed — Intro page: scene briefing + character editor + mode selection
 *
 * Three phases: WorldBriefing → CharacterRoster → LaunchScreen
 *
 * Layout (fixed zones, never move):
 *   Top bar (48px)   — back links (left), slash-mono indicator (center), language (right)
 *   Content area     — phase component, fills between top and bottom bars, overflow hidden
 *   Bottom bar (72px) — action button + skip link
 *
 * Each phase component: h-full overflow-y-auto (owns its own scroll).
 * Mode: prelaunch (live run, editable) vs reference (historical, read-only nav).
 */
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useIntroStore, INTRO_ERROR } from '@/stores/intro'
import { useWorldStore } from '@/stores/world'
import { apiPost, apiPatch } from '@/lib/api'
import { buildNarratorPayload } from '@/lib/narrator'
import { GRAIN_BG } from '@/lib/constants'
import { ArrowLeft, ArrowRight } from '@phosphor-icons/react'
import LanguageSelect from '@/components/LanguageSelect'
import WorldBriefing from './WorldBriefing'
import CharacterRoster from './CharacterRoster'
import LaunchScreen from './LaunchScreen'

type Phase = 0 | 1 | 2

const PHASE_KEYS = ['intro.phaseBriefing', 'intro.phaseCast', 'intro.phaseLaunch'] as const
const TOP_H = 48

export default function IntroPage() {
  const { runId } = useParams<{ runId: string }>()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { phase: activePhase, setPhase, loading, error, fetchIntroData, mode: introMode } = useIntroStore()
  const isReference = introMode === 'reference'
  const fetched = useRef(false)

  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true
    fetchIntroData(runId)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const tid = setTimeout(() => setVisible(true), 100)
    return () => clearTimeout(tid)
  }, [])

  function goPhase(idx: Phase) {
    setVisible(false)
    setTimeout(() => {
      setPhase(idx)
      setTimeout(() => setVisible(true), 50)
    }, 400)
  }

  async function startWorld() {
    const { narratorStyle, narratorPrompt } = useWorldStore.getState()
    await apiPatch('/api/settings', buildNarratorPayload(narratorStyle, narratorPrompt))
    await apiPost('/api/tick/resume')
    navigate(`/run/${runId}/map`)
  }

  const maxPhase: Phase = isReference ? 1 : 2
  function handleAction() {
    if (activePhase < maxPhase) {
      goPhase((activePhase + 1) as Phase)
    } else if (isReference) {
      navigate(`/run/${runId}/map`)
    } else {
      startWorld()
    }
  }

  let actionLabel: string
  if (activePhase < maxPhase) {
    actionLabel = `${t(isReference ? 'intro.next' : 'intro.continue')} →`
  } else if (isReference) {
    actionLabel = `${t('header.backToMap')} →`
  } else {
    actionLabel = t('intro.startWorld')
  }

  /* ── Loading state ── */
  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="font-data text-xs tracking-widest text-muted-foreground uppercase">
          {t('connecting')}
        </p>
      </div>
    )
  }

  /* ── Error state ── */
  if (error) {
    const isNoWorld = error === INTRO_ERROR.NO_WORLD
    const isNoServer = error === INTRO_ERROR.NO_SERVER
    const title = isNoWorld ? t('intro.noActiveWorld') : isNoServer ? t('intro.cannotReachServer') : t('error.somethingWrong')
    const detail = isNoWorld
      ? t('intro.noActiveWorldDetail')
      : isNoServer
        ? t('intro.serverNotRunning')
        : error

    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
        <p className="font-display text-sm font-semibold tracking-wide uppercase text-foreground">{title}</p>
        <p className="font-data text-xs text-muted-foreground max-w-sm text-center leading-relaxed">{detail}</p>
        <div className="flex gap-3 mt-2">
          {!isNoWorld && (
            <button
              onClick={() => { fetched.current = false; fetchIntroData(runId) }}
              className="px-4 py-1.5 text-xs font-display font-semibold tracking-wider uppercase border border-border rounded-sm hover:bg-accent transition-colors cursor-pointer"
            >
              {t('intro.retry')}
            </button>
          )}
          <button
            onClick={() => navigate('/lobby')}
            className="px-4 py-1.5 text-xs font-display font-semibold tracking-wider uppercase border border-border rounded-sm hover:bg-accent transition-colors cursor-pointer"
          >
            {isNoWorld ? t('intro.goToLobby') : t('error.backToLobby')}
          </button>
        </div>
      </div>
    )
  }

  /* ── Main intro flow ── */
  return (
    <div className="relative h-screen bg-background overflow-hidden">
      {/* Grain overlay */}
      <div className="absolute inset-0 pointer-events-none z-0 opacity-[0.015]" style={{ backgroundImage: GRAIN_BG }} />

      {/* ── TOP BAR ── */}
      <div
        className="absolute top-0 left-0 right-0 z-50 grid grid-cols-[1fr_auto_1fr] items-center px-8"
        style={{ height: TOP_H }}
      >
        <div className="flex items-center gap-4 justify-self-start">
          <button
            onClick={() => navigate('/lobby')}
            className="flex items-center gap-1.5 text-[11px] leading-none font-display font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
          >
            <ArrowLeft size={14} />
            {t('header.backToLobby')}
          </button>
          {runId && (
            <button
              onClick={() => navigate(`/run/${runId}/map`)}
              className="flex items-center gap-1.5 text-[11px] leading-none font-display font-semibold text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
            >
              {t('header.backToMap')}
              <ArrowRight size={14} />
            </button>
          )}
        </div>

        <div className="flex items-center justify-self-center">
          {PHASE_KEYS.slice(0, maxPhase + 1).map((key, i) => (
            <div key={i} className="flex items-center">
              <button
                onClick={() => goPhase(i as Phase)}
                className={`text-[11px] leading-none font-data tracking-wider uppercase transition-colors cursor-pointer ${
                  i === activePhase ? 'text-foreground font-bold' : 'text-muted-foreground/30 hover:text-muted-foreground/60'
                }`}
              >
                {t(key)}
              </button>
              {i < maxPhase && <span className="text-muted-foreground/15 mx-2 text-[11px] leading-none">/</span>}
            </div>
          ))}
        </div>

        <div className="justify-self-end">
          <LanguageSelect />
        </div>
      </div>

      {/* ── CONTENT AREA ── */}
      <div
        className={`absolute left-0 right-0 overflow-hidden transition-opacity duration-500 ease-out ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ top: TOP_H, bottom: 0 }}
      >
        {activePhase === 0 ? (
          <WorldBriefing />
        ) : activePhase === 1 ? (
          <CharacterRoster />
        ) : (
          <LaunchScreen />
        )}
      </div>

      {/* ── BOTTOM BAR ── */}
      <div className="absolute bottom-0 left-0 right-0 z-50 flex flex-col items-center justify-end pb-8 pointer-events-none">
        <button
          onClick={handleAction}
          className={`pointer-events-auto font-display text-[13px] font-semibold px-8 py-2 rounded-full border bg-background transition-all duration-300 cursor-pointer ${
            activePhase === maxPhase && !isReference
              ? 'border-foreground text-foreground hover:bg-foreground/5'
              : 'border-foreground/50 text-foreground/80 hover:border-foreground hover:text-foreground'
          }`}
        >
          {actionLabel}
        </button>

        {!isReference && (
          <div className="pointer-events-auto mt-2.5">
            <button
              onClick={startWorld}
              className="text-[10px] font-data tracking-wider text-muted-foreground/60 hover:text-muted-foreground transition-colors cursor-pointer"
            >
              {t('intro.skip')}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
