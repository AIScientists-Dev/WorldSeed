/* WorldSeed — Collage location card for intro briefing */
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CaretDown, CaretUp } from '@phosphor-icons/react'
import { useIntroStore } from '@/stores/intro'
import { Textarea } from '@/components/ui/textarea'
import { uiConfig } from '@/lib/ui-config'

interface Props {
  entity: Record<string, any>
  style: React.CSSProperties
  visible: boolean
}

export default function LocationCard({ entity, style, visible }: Props) {
  const { t } = useTranslation()
  const { updateEntityProperty, mode } = useIntroStore()
  const [editing, setEditing] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)
  const [clamped, setClamped] = useState(false)
  const [desc, setDesc] = useState(entity.description || '')
  const textRef = useRef<HTMLDivElement>(null)

  const imgUrl = uiConfig.vignetteUrl(entity)
  const canEdit = mode === 'prelaunch'

  useEffect(() => {
    const el = textRef.current
    if (!el || expanded) return
    setClamped(el.scrollHeight > el.clientHeight + 1)
  }, [entity.description, expanded, imgFailed])

  async function saveDesc() {
    if (desc !== entity.description) {
      await updateEntityProperty(entity.id, { description: desc })
    }
    setEditing(false)
  }

  return (
    <div
      className={`loc-card rounded-md border border-border/40 bg-card/95 shadow-sm p-4 cursor-default transition-all duration-500 ease-out ${
        visible ? 'opacity-100' : 'opacity-0 translate-y-3'
      } hover:shadow-md hover:border-foreground/20`}
      style={style}
      onClick={(e) => e.stopPropagation()}
    >
      {imgUrl && !imgFailed && (
        <img
          src={imgUrl}
          alt={entity.id}
          className="w-full aspect-[4/3] object-cover rounded-sm mb-2"
          onError={() => setImgFailed(true)}
        />
      )}

      <div className="font-data text-[9px] tracking-[1.5px] text-muted-foreground/40 mb-1.5">
        {entity.type?.toUpperCase() || 'SPACE'}
      </div>

      <div className="font-display text-[13px] font-semibold tracking-wide mb-1.5">
        {entity.id}
      </div>

      {editing ? (
        <Textarea
          value={desc}
          onChange={(e) => setDesc(e.target.value)}
          onBlur={saveDesc}
          onKeyDown={(e) => { if (e.key === 'Escape') { setDesc(entity.description || ''); setEditing(false) } }}
          autoFocus
          className="font-narrative text-[11.5px] leading-relaxed text-muted-foreground min-h-[60px] resize-y bg-muted/30 border-border"
          rows={3}
        />
      ) : (
        <>
          <div
            ref={textRef}
            className={`font-narrative text-[11.5px] leading-relaxed text-muted-foreground ${expanded ? '' : 'line-clamp-3'} ${canEdit ? 'cursor-text' : ''}`}
            onClick={() => canEdit && setEditing(true)}
            title={canEdit ? t('intro.clickToEdit') : undefined}
          >
            {entity.description || '...'}
          </div>
          {clamped && (
            <button
              onClick={() => setExpanded(!expanded)}
              className="flex items-center gap-1 mt-1.5 font-data text-[9px] tracking-wider text-muted-foreground/50 hover:text-foreground transition-colors cursor-pointer"
            >
              {expanded ? <CaretUp size={10} /> : <CaretDown size={10} />}
              {expanded ? t('intro.showLess', '收起') : t('intro.showMore', '展开')}
            </button>
          )}
        </>
      )}
    </div>
  )
}
