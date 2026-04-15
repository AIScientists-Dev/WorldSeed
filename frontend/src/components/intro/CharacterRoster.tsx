/* WorldSeed — Phase 2: Character roster bar + detail panel
 *
 * Pure content — no nav buttons. IntroPage owns all navigation.
 * Roster bar at top, detail panel fills remaining space with internal scroll.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useIntroStore } from '@/stores/intro'
import CharacterDetail from './CharacterDetail'
import { uiConfig } from '@/lib/ui-config'

export default function CharacterRoster() {
  const { t } = useTranslation()
  const { agents, selectedAgentIdx, selectAgent } = useIntroStore()
  const [slotsVisible, setSlotsVisible] = useState(0)
  const [panelVisible, setPanelVisible] = useState(false)

  // Stagger roster entrance
  useEffect(() => {
    let count = 0
    const interval = setInterval(() => {
      count++
      setSlotsVisible(count)
      if (count >= agents.length) {
        clearInterval(interval)
        setTimeout(() => setPanelVisible(true), 200)
      }
    }, 80)
    return () => clearInterval(interval)
  }, [agents.length])

  const selected = agents[selectedAgentIdx] || null

  return (
    <div className="flex flex-col h-full overflow-y-auto px-10 pt-4 pb-32">
      {/* Header label */}
      <div className="shrink-0 font-data text-[11px] tracking-[3px] text-muted-foreground uppercase mb-4 text-center">
        {t('intro.characters')}
      </div>

      {/* Roster bar */}
      <div className="shrink-0 flex gap-1.5 justify-center mb-4 flex-wrap">
        {agents.map((agent, i) => {
          const nameParts = agent.id.split('-')
          const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s
          const role = nameParts.length > 1 ? cap(nameParts[nameParts.length - 1]) : ''
          const name = nameParts.length > 1
            ? nameParts.slice(0, -1).map(cap).join(' ')
            : cap(agent.id)
          const isSelected = i === selectedAgentIdx
          const imgUrl = uiConfig.assetPack
            ? `/assets/scenes/${uiConfig.assetPack}/agents/${agent.id}.png`
            : ''

          return (
            <button
              key={agent.id}
              onClick={() => selectAgent(i)}
              className={`flex flex-col items-center gap-1.5 px-2.5 py-1.5 rounded-lg border-2 transition-all duration-300 ease-out ${
                i < slotsVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
              } ${
                isSelected
                  ? 'border-amber-500 bg-amber-500/[0.08]'
                  : 'border-transparent hover:bg-muted/30'
              }`}
            >
              {/* Portrait */}
              <div
                className={`w-[68px] h-[84px] rounded-md overflow-hidden bg-muted/20 relative flex items-center justify-center transition-all duration-300 ${
                  isSelected
                    ? 'brightness-100 saturate-100 shadow-md'
                    : 'brightness-[0.85] saturate-[0.3] opacity-60'
                }`}
              >
                <span className="font-display text-[22px] font-semibold text-muted-foreground">
                  {name[0]}
                </span>
                {imgUrl && (
                  <img
                    src={imgUrl}
                    alt={name}
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                  />
                )}
              </div>

              {/* Name + role */}
              <div className={`font-display text-xs font-semibold text-center leading-tight transition-colors duration-300 ${
                isSelected ? 'text-foreground' : 'text-muted-foreground'
              }`}>
                {name}
                {role && (
                  <span className="font-data text-[9px] text-muted-foreground tracking-wider block">
                    {role}
                  </span>
                )}
              </div>
            </button>
          )
        })}
      </div>

      {/* Detail panel — fills remaining space, scrolls internally */}
      {selected && (
        <div className={`flex-1 min-h-0 w-full max-w-[900px] mx-auto transition-all duration-500 ease-out ${
          panelVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-5'
        }`}>
          <CharacterDetail agent={selected} />
        </div>
      )}
    </div>
  )
}
