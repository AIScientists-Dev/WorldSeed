/* WorldSeed — Demo intro: scene briefing + character roster.
 *
 * Two phases only (no LaunchScreen). Composes WorldBriefing + CharacterRoster.
 * Simplified top bar — phase indicators only, no back links.
 * Bottom button navigates to /demo/map on final phase.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useIntroStore, INTRO_ERROR } from '@/stores/intro'
import { useDemoStore } from '@/stores/demo'
import { GRAIN_BG } from '@/lib/constants'
import WorldBriefing from '@/components/intro/WorldBriefing'
import CharacterRoster from '@/components/intro/CharacterRoster'

type Phase = 0 | 1

const PHASE_KEYS = ['intro.phaseBriefing', 'intro.phaseCast'] as const
const TOP_H = 48

export default function DemoIntroPage() {
  const runId = useDemoStore(s => s.runId)
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { phase: activePhase, setPhase, loading, error, fetchIntroData } = useIntroStore()
  const fetched = useRef(false)
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (fetched.current || !runId) return
    fetched.current = true
    fetchIntroData(runId)
  }, [runId]) // eslint-disable-line react-hooks/exhaustive-deps

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

  const maxPhase: Phase = 1

  function handleAction() {
    if (activePhase < maxPhase) {
      goPhase(1)
    } else {
      navigate('/demo/map')
    }
  }

  const actionLabel = activePhase < maxPhase
    ? `${t('intro.next')} →`
    : `${t('intro.enterWorld')} →`

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="font-data text-xs tracking-widest text-muted-foreground uppercase">
          {t('connecting')}
        </p>
      </div>
    )
  }

  if (error) {
    const isNoServer = error === INTRO_ERROR.NO_SERVER
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4 bg-background">
        <p className="font-display text-sm font-semibold tracking-wide uppercase text-foreground">
          {isNoServer ? t('intro.cannotReachServer') : t('error.somethingWrong')}
        </p>
        <button
          onClick={() => { fetched.current = false; fetchIntroData(runId) }}
          className="px-4 py-1.5 text-xs font-display font-semibold tracking-wider uppercase border border-border rounded-sm hover:bg-accent transition-colors cursor-pointer"
        >
          {t('intro.retry')}
        </button>
      </div>
    )
  }

  return (
    <div className="relative h-screen bg-background overflow-hidden">
      {/* Grain overlay */}
      <div className="absolute inset-0 pointer-events-none z-0 opacity-[0.015]" style={{ backgroundImage: GRAIN_BG }} />

      {/* Top bar — phase indicators */}
      <div
        className="absolute top-0 left-0 right-0 z-50 flex items-center justify-center px-8"
        style={{ height: TOP_H }}
      >
        {PHASE_KEYS.map((key, i) => (
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

      {/* Content */}
      <div
        className={`absolute left-0 right-0 overflow-hidden transition-opacity duration-500 ease-out ${
          visible ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ top: TOP_H, bottom: 0 }}
      >
        {activePhase === 0 ? <WorldBriefing /> : <CharacterRoster />}
      </div>

      {/* Bottom action button */}
      <div className="absolute bottom-0 left-0 right-0 z-50 flex flex-col items-center justify-end pb-8 pointer-events-none">
        <button
          onClick={handleAction}
          className={`pointer-events-auto font-display text-[13px] font-semibold px-8 py-2 rounded-full border bg-background transition-all duration-300 cursor-pointer ${
            activePhase === maxPhase
              ? 'border-foreground text-foreground hover:bg-foreground/5'
              : 'border-foreground/50 text-foreground/80 hover:border-foreground hover:text-foreground'
          }`}
        >
          {actionLabel}
        </button>
      </div>
    </div>
  )
}
