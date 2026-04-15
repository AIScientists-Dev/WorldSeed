import { useTranslation } from 'react-i18next'
import { useLobbyStore } from '@/stores/lobby'
import type { ProviderGroup } from '@/stores/lobby'
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectSeparator, SelectTrigger, SelectValue } from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { Input } from '@/components/ui/input'
import { LS_DM_MODEL } from '@/lib/constants'

interface Props {
  triggerClassName?: string
  compact?: boolean
}

export default function DmModelSelect({ triggerClassName, compact }: Props) {
  const { t } = useTranslation()
  const dmModel = useLobbyStore(s => s.dmModel)
  const availableModels = useLobbyStore(s => s.availableModels)
  const modelsLoaded = useLobbyStore(s => s.modelsLoaded)
  const customModel = useLobbyStore(s => s.customModel)

  const base = compact ? 'text-xs' : 'text-[13px]'
  const font = cn('font-[family-name:var(--font-data)]', base)
  const triggerCls = cn(font, triggerClassName)

  // Custom input mode
  if (customModel) {
    return (
      <div className="flex gap-1.5 items-center">
        <Input
          value={dmModel}
          onChange={e => { useLobbyStore.setState({ dmModel: e.target.value }); localStorage.setItem(LS_DM_MODEL, e.target.value) }}
          placeholder={t('lobby.dmModelPlaceholder')}
          className={cn('flex-1', font)}
        />
        <button
          type="button"
          className="text-xs text-muted-foreground hover:text-foreground px-2 shrink-0"
          onClick={() => useLobbyStore.setState({ customModel: false })}
        >
          &larr;
        </button>
      </div>
    )
  }

  // No API keys — nothing to show (warning is in LobbyPage)
  if (modelsLoaded && availableModels.length === 0) {
    return null
  }

  // Loading
  if (!modelsLoaded) {
    return (
      <Select disabled>
        <SelectTrigger className={triggerCls}>
          <SelectValue placeholder={t('lobby.dmModelLoading')} />
        </SelectTrigger>
      </Select>
    )
  }

  // Normal: grouped model select
  const flatModels = availableModels.flatMap(g => g.models.map(m => m.id))
  const valueInList = flatModels.includes(dmModel) || !dmModel

  return (
    <Select
      value={valueInList ? dmModel : '__custom__'}
      onValueChange={v => {
        if (v === '__custom__') {
          useLobbyStore.setState({ customModel: true })
        } else {
          useLobbyStore.setState({ dmModel: v }); localStorage.setItem(LS_DM_MODEL, v)
        }
      }}
    >
      <SelectTrigger className={triggerCls}>
        <SelectValue placeholder={t('lobby.dmModelPlaceholder')} />
      </SelectTrigger>
      <SelectContent>
        {availableModels.map((g: ProviderGroup) => (
          <SelectGroup key={g.provider}>
            <SelectLabel className="font-[family-name:var(--font-display)] text-[10px] uppercase tracking-wider text-muted-foreground">
              {g.provider}
            </SelectLabel>
            {g.models.map(m => (
              <SelectItem key={m.id} value={m.id} className={cn('font-[family-name:var(--font-data)]', compact ? 'text-[11px]' : 'text-[12px]')}>
                {m.id}
              </SelectItem>
            ))}
          </SelectGroup>
        ))}
        <SelectSeparator />
        <SelectItem value="__custom__" className={cn('font-[family-name:var(--font-data)]', compact ? 'text-[11px]' : 'text-[12px]', 'text-muted-foreground')}>
          {t('lobby.dmModelCustom')}
        </SelectItem>
      </SelectContent>
    </Select>
  )
}
