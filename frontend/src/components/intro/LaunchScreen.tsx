/* WorldSeed — Phase 3: Launch screen — narrator + pacing selection
 *
 * Pure content — no nav buttons. IntroPage owns all navigation.
 * Section 1: Narrator voice (compact trigger → expandable picker)
 * Section 2: Pacing mode (Free Flow vs Chapter Pause)
 */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useUIStore, type ChronicleMode } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { NARRATOR_STYLES, narratorDescKey, type NarratorStyle } from '@/lib/narrator'
import { LS_NARRATOR_STYLE, LS_NARRATOR_PROMPT } from '@/lib/constants'
import { Wind, BookOpen, CaretDown } from '@phosphor-icons/react'
import { Textarea } from '@/components/ui/textarea'
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover'

const MODES = ['auto', 'step'] as const
const PICKER_OPTIONS: readonly (NarratorStyle)[] = [...NARRATOR_STYLES, 'custom']

export default function LaunchScreen() {
  const { t } = useTranslation()
  const selectedMode = useUIStore(s => s.chronicleMode)
  const selectedNarrator = useWorldStore(s => s.narratorStyle)
  const customPrompt = useWorldStore(s => s.narratorPrompt)
  const [pickerOpen, setPickerOpen] = useState(false)
  const [cardsIn, setCardsIn] = useState(false)
  const promptTimer = useRef<ReturnType<typeof setTimeout>>(null)

  useEffect(() => {
    const tid = setTimeout(() => setCardsIn(true), 150)
    return () => {
      clearTimeout(tid)
      clearTimeout(promptTimer.current)
    }
  }, [])

  function selectMode(mode: ChronicleMode) {
    localStorage.setItem('ws-chronicle-mode', mode)
    useUIStore.setState({ chronicleMode: mode })
  }

  function selectNarrator(style: NarratorStyle) {
    localStorage.setItem(LS_NARRATOR_STYLE, style)
    useWorldStore.setState({ narratorStyle: style })
    if (style !== 'custom') setPickerOpen(false)
  }

  function updateCustomPrompt(value: string) {
    useWorldStore.setState({ narratorPrompt: value })
    // Debounce localStorage write — no need to hit disk on every keystroke
    clearTimeout(promptTimer.current)
    promptTimer.current = setTimeout(() => localStorage.setItem(LS_NARRATOR_PROMPT, value), 300)
  }

  const modeConfig = {
    auto: { icon: Wind, name: t('intro.flowMode'), desc: t('intro.flowDescription') },
    step: { icon: BookOpen, name: t('intro.chapterMode'), desc: t('intro.chapterDescription') },
  } as const

  return (
    <div className="flex flex-col items-center h-full overflow-y-auto px-10 pb-32">
      {/* Spacer wrapper — centers content vertically when viewport is tall, scrolls when short */}
      <div className="my-auto flex flex-col items-center pt-8 pb-12 w-full">
      {/* ── Narrator voice ── */}
      <div
        className={`w-full max-w-[560px] mb-10 transition-all duration-700 ${
          cardsIn ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'
        }`}
      >
        <div
          className="text-[10px] tracking-[4px] text-muted-foreground/60 uppercase mb-4 text-center"
          style={{ fontFamily: 'var(--font-data)' }}
        >
          {t('narrator.sectionTitle')}
        </div>

        <Popover open={pickerOpen} onOpenChange={setPickerOpen}>
          <PopoverTrigger asChild>
            <button className="w-full flex items-center justify-between px-5 py-3.5 rounded-xl border border-border/60 hover:border-border transition-colors cursor-pointer text-left">
              <div>
                <div
                  className="text-[15px] font-semibold text-foreground"
                  style={{ fontFamily: 'var(--font-display)' }}
                >
                  {t(`narrator.${selectedNarrator}`)}
                </div>
                <div
                  className="text-[12px] text-muted-foreground mt-0.5"
                  style={{ fontFamily: 'var(--font-narrative)' }}
                >
                  {t(narratorDescKey(selectedNarrator))}
                </div>
              </div>
              <CaretDown
                size={14}
                className={`text-muted-foreground/50 transition-transform ${pickerOpen ? 'rotate-180' : ''}`}
              />
            </button>
          </PopoverTrigger>

          <PopoverContent
            align="start"
            sideOffset={6}
            className="w-[var(--radix-popover-trigger-width)] p-0 rounded-xl border-border/60 max-h-[50vh] overflow-y-auto"
          >
            {PICKER_OPTIONS.map((style, i) => (
              <button
                key={style}
                onClick={() => selectNarrator(style)}
                className={`w-full flex items-center justify-between px-5 py-2.5 text-left transition-colors cursor-pointer ${
                  i === NARRATOR_STYLES.length ? 'border-t border-border/40' : ''
                } ${
                  selectedNarrator === style
                    ? 'bg-foreground/[0.06]'
                    : 'hover:bg-muted/50'
                }`}
              >
                <div>
                  <span
                    className={`text-[13px] font-medium ${
                      selectedNarrator === style ? 'text-foreground' : 'text-foreground/80'
                    }`}
                    style={{ fontFamily: 'var(--font-display)' }}
                  >
                    {t(`narrator.${style}`)}
                  </span>
                  <span
                    className="ml-2 text-[11px] text-muted-foreground"
                    style={{ fontFamily: 'var(--font-narrative)' }}
                  >
                    {t(narratorDescKey(style))}
                  </span>
                </div>
                {selectedNarrator === style && (
                  <div className="w-1.5 h-1.5 rounded-full bg-foreground shrink-0" />
                )}
              </button>
            ))}
            {selectedNarrator === 'custom' && (
              <div className="border-t border-border/40 p-3">
                <Textarea
                  value={customPrompt}
                  onChange={e => updateCustomPrompt(e.target.value)}
                  placeholder={t('narrator.customPlaceholder')}
                  rows={3}
                  className="text-[13px] leading-relaxed border-border/60 resize-vertical"
                  style={{ fontFamily: 'var(--font-narrative)' }}
                />
              </div>
            )}
          </PopoverContent>
        </Popover>
      </div>

      {/* ── Pacing mode ── */}
      <div
        className="text-[10px] tracking-[4px] text-muted-foreground/60 uppercase mb-6 transition-opacity duration-700"
        style={{ fontFamily: 'var(--font-data)', opacity: cardsIn ? 1 : 0 }}
      >
        {t('intro.experienceMode')}
      </div>

      <div className="flex gap-8">
        {MODES.map((key, i) => {
          const mode = modeConfig[key]
          const active = selectedMode === key
          const Icon = mode.icon
          return (
            <button
              key={key}
              onClick={() => selectMode(key)}
              className={`relative flex flex-col items-center w-[260px] py-12 px-8 rounded-2xl border-2 transition-all duration-400 cursor-pointer ${
                cardsIn
                  ? 'opacity-100 translate-y-0'
                  : 'opacity-0 translate-y-6'
              } ${
                active
                  ? 'border-foreground bg-foreground/[0.06] shadow-[0_8px_50px_rgba(0,0,0,0.12)] scale-[1.02]'
                  : 'border-border/50 opacity-55 hover:opacity-75 hover:border-border'
              }`}
              style={{ transitionDelay: cardsIn ? `${i * 120}ms` : '0ms' }}
            >
              <div className={`mb-5 transition-all duration-300 ${
                active ? 'text-foreground' : 'text-muted-foreground'
              }`}>
                <Icon size={36} weight={active ? 'duotone' : 'light'} />
              </div>

              <div
                className={`text-[20px] font-bold tracking-wide transition-colors duration-300 ${
                  active ? 'text-foreground' : 'text-muted-foreground'
                }`}
                style={{ fontFamily: 'var(--font-display)' }}
              >
                {mode.name}
              </div>

              <div
                className={`mt-4 text-[14px] leading-[1.8] text-center transition-colors duration-300 ${
                  active ? 'text-foreground/70' : 'text-muted-foreground'
                }`}
                style={{ fontFamily: 'var(--font-narrative)' }}
              >
                {mode.desc}
              </div>

              <div className={`mt-6 w-2 h-2 rounded-full transition-all duration-300 ${
                active ? 'bg-foreground scale-100' : 'bg-muted-foreground/30 scale-75'
              }`} />
            </button>
          )
        })}
      </div>

      <div
        className={`mt-8 text-[10px] tracking-wider text-muted-foreground/40 transition-opacity duration-500 ${
          cardsIn ? 'opacity-100' : 'opacity-0'
        }`}
        style={{ fontFamily: 'var(--font-data)' }}
      >
        {t('intro.modeHint')}
      </div>
      </div>
    </div>
  )
}
