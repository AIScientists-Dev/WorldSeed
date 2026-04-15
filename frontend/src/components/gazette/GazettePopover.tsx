import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate, useParams } from 'react-router-dom'
import { Newspaper } from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useGazetteStore } from '@/stores/gazette'
import { useWorldStore } from '@/stores/world'
import { useDemoStore } from '@/stores/demo'

export default function GazettePopover() {
  const { t } = useTranslation()
  const { runId: paramRunId } = useParams<{ runId: string }>()
  const storeRunId = useWorldStore(s => s.viewingRunId)
  const runId = paramRunId || storeRunId
  const navigate = useNavigate()
  const isDemo = useDemoStore(s => s.active)
  const [open, setOpen] = useState(false)

  const status = useGazetteStore(s => s.status)
  const editions = useGazetteStore(s => s.editions)
  const estimate = useGazetteStore(s => s.estimate)
  const noModel = useGazetteStore(s => s.noModel)
  const error = useGazetteStore(s => s.error)
  const generatingStartedAt = useGazetteStore(s => s.generatingStartedAt)
  const language = useGazetteStore(s => s.language)
  const setLanguage = useGazetteStore(s => s.setLanguage)
  const fetchList = useGazetteStore(s => s.fetchList)
  const generate = useGazetteStore(s => s.generate)
  const reset = useGazetteStore(s => s.reset)

  // Elapsed time ticker during generation
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (status !== 'generating' || !generatingStartedAt) return
    const interval = setInterval(() => {
      setElapsed(Math.floor((Date.now() - generatingStartedAt) / 1000))
    }, 1000)
    return () => clearInterval(interval)
  }, [status, generatingStartedAt])

  // Fetch list on popover open
  useEffect(() => {
    if (open && runId && status === 'idle') {
      fetchList(runId)
    }
  }, [open, runId, status, fetchList])

  function handleOpenChange(v: boolean) {
    setOpen(v)
    if (!v && status !== 'generating') reset()
  }

  function handleGenerate() {
    if (runId) generate(runId)
  }

  function handleView(gazetteId: string) {
    setOpen(false)
    navigate(`/run/${runId}/gazette?id=${gazetteId}`)
  }

  const hasEditions = editions.length > 0

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <Tooltip>
        <TooltipTrigger asChild>
          <PopoverTrigger asChild>
            <Button variant="ghost" size="xs">
              <Newspaper size={12} />
              {t('gazette.title')}
            </Button>
          </PopoverTrigger>
        </TooltipTrigger>
        <TooltipContent>{t('gazette.generateTooltip')}</TooltipContent>
      </Tooltip>

      <PopoverContent className="w-80 p-4" align="end">
        <div className="text-sm font-medium mb-2">{t('gazette.title')}</div>

        {status === 'loading' && (
          <p className="text-xs text-muted-foreground">{t('gazette.loading')}</p>
        )}

        {/* Existing editions */}
        {status === 'loaded' && hasEditions && (
          <div className="space-y-1.5 mb-3">
            <div className="text-[10px] font-medium text-muted-foreground tracking-wider uppercase">
              {editions.length} {t('gazette.editions')}
            </div>
            {editions.map((ed) => (
              <button
                key={ed.id}
                className="w-full text-left px-2 py-1.5 rounded hover:bg-accent/50 transition-colors"
                onClick={() => handleView(ed.id)}
              >
                <div className="text-xs font-medium truncate">{ed.edition_title || t('gazette.untitled')}</div>
                <div className="text-[10px] text-muted-foreground flex gap-2">
                  <span>{ed.language}</span>
                  <span className="tabular-nums">${ed.cost_usd.toFixed(3)}</span>
                  <span>{ed.created_at.replace('_', ' ')}</span>
                </div>
              </button>
            ))}
          </div>
        )}

        {/* Generate new */}
        {status === 'loaded' && !noModel && estimate && (
          <>
            {hasEditions && <Separator className="my-2" />}
            <div className="space-y-2">
              <div className="text-[10px] font-medium text-muted-foreground tracking-wider uppercase">
                {hasEditions ? t('gazette.newEdition') : t('gazette.generate')}
              </div>
              <div className="text-xs space-y-0.5">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('gazette.model')}</span>
                  <span className="font-mono">{estimate.model.split('/').pop()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('gazette.input')}</span>
                  <span className="tabular-nums">~{(estimate.input_tokens / 1000).toFixed(1)}K tokens</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">{t('gazette.estCost')}</span>
                  <span className="tabular-nums">~${estimate.estimated_cost_usd.toFixed(3)}</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-muted-foreground">{t('gazette.language')}</span>
                  <Select value={language} onValueChange={setLanguage}>
                    <SelectTrigger className="h-6 w-28 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="English">English</SelectItem>
                      <SelectItem value="Chinese (中文)">中文</SelectItem>
                      <SelectItem value="Japanese (日本語)">日本語</SelectItem>
                      <SelectItem value="Korean (한국어)">한국어</SelectItem>
                      <SelectItem value="Spanish (Español)">Español</SelectItem>
                      <SelectItem value="French (Français)">Français</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button size="sm" className="w-full mt-1" onClick={handleGenerate}>
                {hasEditions ? t('gazette.generateNewEdition') : t('gazette.generateGazette')}
              </Button>
            </div>
          </>
        )}

        {/* No model configured */}
        {status === 'loaded' && noModel && !hasEditions && (
          <p className="text-xs text-muted-foreground">
            {t('gazette.noModel')}
          </p>
        )}

        {/* Generating */}
        {status === 'generating' && (
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <div className="h-3 w-3 rounded-full border-2 border-primary border-t-transparent animate-spin" />
              <span className="text-xs tabular-nums">{t('gazette.generating', { seconds: elapsed })}</span>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('gazette.generatingHint')}
              {estimate && (
                <span className="block mt-1 tabular-nums">
                  {estimate.estimated_cost_usd < 0.05 ? t('gazette.typicallyFast') : t('gazette.typicallySlow')}
                </span>
              )}
            </p>
          </div>
        )}

        {/* Error */}
        {status === 'error' && (
          <div className="space-y-2">
            <p className="text-xs text-destructive">{error}</p>
            <Button size="sm" variant="outline" className="w-full" onClick={() => runId && fetchList(runId)}>
              {t('gazette.retry')}
            </Button>
          </div>
        )}
      </PopoverContent>
    </Popover>
  )
}
