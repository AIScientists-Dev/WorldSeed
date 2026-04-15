/* WorldSeed — Demo welcome: language selection before intro phases.
 *
 * Matches lobby/setup visual style (setup-brand, font tokens, spacing).
 * Shown only in demo mode, before any phase content.
 */

import { useState } from 'react'
import { LANGUAGES, setLanguage } from '@/i18n'
import { apiPatch } from '@/lib/api'
import { GRAIN_BG } from '@/lib/constants'

const DEMO_LANGUAGES = LANGUAGES.filter(l => l.code === 'en' || l.code === 'zh')

interface Props {
  onSelect: (lang: string) => void
}

export default function DemoWelcome({ onSelect }: Props) {
  const [visible, setVisible] = useState(true)

  function choose(lang: string) {
    setLanguage(lang)
    apiPatch('/api/settings', { language: lang })
    setVisible(false)
    setTimeout(() => onSelect(lang), 500)
  }

  return (
    <div className={`relative flex h-screen flex-col items-center justify-center bg-[var(--bg-void)] transition-opacity duration-500 ${visible ? 'opacity-100' : 'opacity-0'}`}>
      {/* Grain overlay — same as IntroPage */}
      <div className="absolute inset-0 pointer-events-none z-0 opacity-[0.015]" style={{ backgroundImage: GRAIN_BG }} />

      <div className="relative z-10 flex flex-col items-center">
        {/* Brand — matches .setup-brand */}
        <div className="setup-brand">WORLD<em>SEED</em></div>

        {/* Subtitle — matches .setup-subtitle */}
        <div className="setup-subtitle">Persistent World Engine</div>

        {/* Language buttons */}
        <div className="flex flex-col gap-3 w-[260px] mt-6">
          {DEMO_LANGUAGES.map(l => (
            <button
              key={l.code}
              onClick={() => choose(l.code)}
              className="flex items-center justify-between px-5 py-3 rounded-[var(--radius)] border border-[var(--border)] hover:border-[var(--amber)] hover:bg-[var(--amber-dim)] transition-all cursor-pointer"
            >
              <span
                className="text-[14px] font-semibold text-[var(--bright)]"
                style={{ fontFamily: 'var(--font-display)' }}
              >
                {l.name}
              </span>
              <span
                className="text-[11px] tracking-[2px] text-[var(--ghost)]"
                style={{ fontFamily: 'var(--font-data)' }}
              >
                {l.label}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
