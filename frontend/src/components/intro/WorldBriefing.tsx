/* WorldSeed — Phase 1: Scene briefing with typewriter + collage location cards
 *
 * Pure content — no nav buttons. IntroPage owns all navigation.
 * Click anywhere to skip the typewriter animation.
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useIntroStore } from '@/stores/intro'
import LocationCard from './LocationCard'

export default function WorldBriefing() {
  const { t } = useTranslation()
  const { scene, entities, typewriterDone, finishTypewriter } = useIntroStore()
  const [displayText, setDisplayText] = useState('')
  const [showCursor, setShowCursor] = useState(true)
  const [cardsVisible, setCardsVisible] = useState(false)
  const [visibleCardCount, setVisibleCardCount] = useState(0)
  const charIdx = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout>>(null)
  const fullText = scene?.description || ''

  const locations = entities.filter((e) => e.type === 'space')

  // Typewriter effect
  const typeNext = useCallback(() => {
    if (charIdx.current >= fullText.length) {
      finishTypewriter()
      setShowCursor(false)
      setCardsVisible(true)
      return
    }
    charIdx.current++
    setDisplayText(fullText.slice(0, charIdx.current))
    const ch = fullText[charIdx.current - 1]
    const delay = ch === '\u3002' ? 300 : ch === '\uff0c' ? 150 : ch === '\u2014' ? 80 : 45
    timerRef.current = setTimeout(typeNext, delay)
  }, [fullText, finishTypewriter])

  useEffect(() => {
    if (typewriterDone) {
      setDisplayText(fullText)
      setShowCursor(false)
      setCardsVisible(true)
      return
    }
    if (fullText) {
      timerRef.current = setTimeout(typeNext, 600)
    }
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [fullText, typewriterDone, typeNext])

  // Click to skip typewriter
  function handleClick(e: React.MouseEvent) {
    if ((e.target as HTMLElement).closest('button')) return
    if ((e.target as HTMLElement).closest('.loc-card')) return
    if (!typewriterDone) {
      if (timerRef.current) clearTimeout(timerRef.current)
      charIdx.current = fullText.length
      setDisplayText(fullText)
      setShowCursor(false)
      finishTypewriter()
      setCardsVisible(true)
    }
  }

  // Stagger card reveal
  useEffect(() => {
    if (!cardsVisible) return
    let count = 0
    const interval = setInterval(() => {
      count++
      setVisibleCardCount(count)
      if (count >= locations.length) clearInterval(interval)
    }, 150)
    return () => clearInterval(interval)
  }, [cardsVisible, locations.length])

  const cols = Math.min(locations.length, 3)
  const cardW = 190

  return (
    <div
      className="flex flex-col items-center h-full overflow-y-auto px-10 pt-4 pb-32"
      onClick={handleClick}
    >
      {/* Badge */}
      <div className="shrink-0 font-data text-[11px] tracking-[3px] text-muted-foreground uppercase mb-5">
        {t('brand')} · {scene?.id || ''}
      </div>

      {/* Scene description — typewriter */}
      <div className="shrink-0 max-w-[680px] w-full">
        <div className="font-narrative text-[17px] leading-8 text-muted-foreground text-left pr-2">
          {displayText}
          {showCursor && (
            <span className="inline-block w-[2px] h-[1em] bg-amber-500 ml-0.5 align-text-bottom animate-[tw-blink_1s_step-end_infinite]" />
          )}
        </div>
      </div>

      {/* Location cards — grid */}
      {cardsVisible && locations.length > 0 && (
        <div
          className="mt-6 w-full max-w-[620px] grid gap-3"
          style={{ gridTemplateColumns: `repeat(${cols}, ${cardW}px)`, justifyContent: 'center' }}
        >
          {locations.map((loc, i) => (
            <LocationCard
              key={loc.id}
              entity={loc}
              style={{ width: cardW }}
              visible={i < visibleCardCount}
            />
          ))}
        </div>
      )}
    </div>
  )
}
