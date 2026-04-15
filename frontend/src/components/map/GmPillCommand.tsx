/* GmPill — Command mode input.
 * Renders: [input] [send button]
 * Parent handles tabs and expand/collapse.
 */

import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/stores/ui'
import { useCommands } from '@/hooks/useCommands'
import { Button } from '@/components/ui/button'
import { ArrowUp } from '@phosphor-icons/react'
import { useDemoStore } from '@/stores/demo'

export default function GmPillCommand() {
  const { t } = useTranslation()
  const gmResolveText = useUIStore(s => s.gmResolveText)
  const gmFeedback = useUIStore(s => s.gmFeedback)
  const { cmdGmResolve } = useCommands()
  const isDemo = useDemoStore(s => s.active)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const id = setTimeout(() => inputRef.current?.focus(), 60)
    return () => clearTimeout(id)
  }, [])

  function handleSubmit() {
    if (!gmResolveText.trim()) return
    cmdGmResolve()
  }

  return (
    <>
      <input
        ref={inputRef}
        type="text"
        className="min-w-0 flex-1 bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground"
        placeholder={isDemo ? t('gm.demoHint') : t('gm.commandPlaceholder')}
        disabled={isDemo}
        value={gmResolveText}
        onChange={e => useUIStore.setState({ gmResolveText: e.target.value })}
        onKeyDown={e => {
          if (e.key === 'Enter') { e.preventDefault(); handleSubmit() }
        }}
      />
      {gmFeedback && (
        <span className="shrink-0 text-[10px] text-muted-foreground">{gmFeedback}</span>
      )}
      <Button
        size="icon-xs"
        className="shrink-0 rounded-full"
        disabled={isDemo || !gmResolveText.trim()}
        onClick={handleSubmit}
      >
        <ArrowUp size={12} />
      </Button>
    </>
  )
}
