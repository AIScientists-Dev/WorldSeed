/* GmPill — Whisper mode input.
 * Renders: [agent select] [input] [send button]
 * After send, selects agent on map to open their detail panel.
 */

import { useEffect, useRef, useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useUIStore } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { useCommands } from '@/hooks/useCommands'
import { useMapSelection } from '@/components/MapSelectionContext'
import { humanize } from '@/lib/helpers'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ArrowUp, CircleNotch } from '@phosphor-icons/react'
import { toast } from 'sonner'
import { useDemoStore } from '@/stores/demo'

interface Props {
  preSelectedAgentId: string | null
}

export default function GmPillWhisper({ preSelectedAgentId }: Props) {
  const { t } = useTranslation()
  const whisperText = useUIStore(s => s.whisperText)
  const entities = useWorldStore(s => s.entities)
  const agents = useMemo(() => entities.filter(e => e.type === 'agent'), [entities])
  const { cmdWhisper } = useCommands()
  const { setSelectedId } = useMapSelection()
  const isDemo = useDemoStore(s => s.active)
  const inputRef = useRef<HTMLInputElement>(null)

  const validPreselect = preSelectedAgentId && agents.some(a => a.id === preSelectedAgentId) ? preSelectedAgentId : ''
  const [agentId, setAgentId] = useState(validPreselect)
  const [sending, setSending] = useState(false)

  const agentName = useMemo(() => {
    const a = agents.find(a => a.id === agentId)
    return a ? humanize(a.id) : ''
  }, [agentId, agents])

  useEffect(() => {
    if (agentId) setTimeout(() => inputRef.current?.focus(), 60)
  }, [agentId])

  async function handleSubmit() {
    if (!agentId || !whisperText.trim() || sending) return
    setSending(true)
    const { ok } = await cmdWhisper(agentId)
    setSending(false)
    if (ok) {
      setSelectedId(agentId)
    } else {
      toast.error(t('gm.noActiveWorld'))
    }
  }

  return (
    <>
      <Select value={agentId || undefined} onValueChange={setAgentId}>
        <SelectTrigger className="h-6 w-auto shrink-0 gap-1 rounded-md border-0 bg-transparent px-1.5 font-[family-name:var(--font-data)] text-[11px] text-foreground shadow-none hover:bg-secondary/40 [&>svg]:size-3 [&>svg]:opacity-40">
          <SelectValue placeholder={t('gm.selectAgent')} />
        </SelectTrigger>
        <SelectContent align="start" className="max-h-[200px]">
          {agents.map(a => (
            <SelectItem key={a.id} value={a.id} className="text-xs">
              {humanize(a.id)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <input
        ref={inputRef}
        type="text"
        className="min-w-0 flex-1 bg-transparent text-[12.5px] text-foreground outline-none placeholder:text-muted-foreground disabled:opacity-40"
        placeholder={isDemo ? t('gm.demoHint') : agentId ? t('gm.whisperPlaceholder', { agent: agentName }) : t('gm.selectAgent')}
        disabled={isDemo || !agentId || sending}
        value={whisperText}
        onChange={e => useUIStore.setState({ whisperText: e.target.value })}
        onKeyDown={e => {
          if (e.key === 'Enter') { e.preventDefault(); handleSubmit() }
        }}
      />
      <Button
        size="icon-xs"
        className="shrink-0 rounded-full"
        disabled={isDemo || !agentId || !whisperText.trim() || sending}
        onClick={handleSubmit}
      >
        {sending ? <CircleNotch size={12} className="animate-spin" /> : <ArrowUp size={12} />}
      </Button>
    </>
  )
}
