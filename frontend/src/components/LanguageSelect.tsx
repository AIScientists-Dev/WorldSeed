/* WorldSeed — Shared language selector
 *
 * Used in HeaderBar, IntroPage, and LobbyPage.
 * Changes both frontend i18n locale and backend engine language.
 */
import { useTranslation } from 'react-i18next'
import { setLanguage, LANGUAGES } from '@/i18n'
import { apiPatch } from '@/lib/api'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'

interface LanguageSelectProps {
  /** Extra callback after language change (e.g. sync lobby store). */
  onChange?: (lang: string) => void
}

export default function LanguageSelect({ onChange }: LanguageSelectProps) {
  const { i18n } = useTranslation()

  function switchLanguage(lang: string) {
    setLanguage(lang)
    apiPatch('/api/settings', { language: lang })
    onChange?.(lang)
  }

  return (
    <Select value={i18n.language} onValueChange={switchLanguage}>
      <SelectTrigger className="h-7 w-auto gap-0 border-0 bg-transparent px-1.5 py-0 font-[family-name:var(--font-display)] text-[11px] leading-none font-semibold tracking-wider text-muted-foreground shadow-none hover:text-foreground [&>span]:translate-y-px [&>svg]:ml-0.5 [&>svg]:size-2.5 [&>svg]:opacity-30">
        <SelectValue />
      </SelectTrigger>
      <SelectContent align="end" className="min-w-[120px]">
        {LANGUAGES.map(l => (
          <SelectItem key={l.code} value={l.code} className="text-xs">
            <span className="font-[family-name:var(--font-display)] font-semibold tracking-wider">{l.label}</span>
            <span className="ml-2 text-muted-foreground">{l.name}</span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
