/* WorldSeed — Character detail: tarot card + slide card (one section at a time) */
import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useIntroStore, type IntroAgent } from '@/stores/intro'
import { Textarea } from '@/components/ui/textarea'
import { Input } from '@/components/ui/input'
import { Lock, PencilSimple, Check, CaretLeft, CaretRight } from '@phosphor-icons/react'
import { uiConfig } from '@/lib/ui-config'
import { formatVal } from '@/lib/helpers'

interface Props {
  agent: IntroAgent
}

interface Section {
  key: string
  label: string
  type: 'character' | 'properties'
  value: any
  hidden?: boolean
}

const HIDDEN_KEYS: string[] = []

export default function CharacterDetail({ agent }: Props) {
  const { t } = useTranslation()
  const { editing, toggleEditing, updateCharacter, updateAgentProperty, mode } = useIntroStore()
  const canEdit = mode === 'prelaunch'
  const [sectionIdx, setSectionIdx] = useState(0)
  const nameParts = agent.id.split('-')
  const cap = (s: string) => s ? s[0].toUpperCase() + s.slice(1) : s
  const role = nameParts.length > 1 ? cap(nameParts[nameParts.length - 1]) : ''
  const name = nameParts.length > 1
    ? nameParts.slice(0, -1).map(cap).join(' ')
    : cap(agent.id)

  const imgUrl = uiConfig.assetPack
    ? `/assets/scenes/${uiConfig.assetPack}/agents/${agent.id}.png`
    : ''

  const fieldLabel = (key: string) => t(`intro.fields.${key}`, { defaultValue: key.replace(/_/g, ' ') })

  // Build sections list
  const sections: Section[] = [
    ...Object.entries(agent.character).map(([k, v]) => ({
      key: k,
      label: fieldLabel(k),
      type: 'character' as const,
      value: v,
      hidden: HIDDEN_KEYS.includes(k),
    })),
  ]

  const propEntries = Object.entries(agent.properties).filter(([k]) => k !== 'constraints')
  if (propEntries.length > 0) {
    sections.push({
      key: '_properties',
      label: t('intro.properties'),
      type: 'properties',
      value: Object.fromEntries(propEntries),
    })
  }

  // Reset section index on agent switch
  useEffect(() => { setSectionIdx(0) }, [agent.id])

  const current = sections[sectionIdx] || sections[0]
  const canPrev = sectionIdx > 0
  const canNext = sectionIdx < sections.length - 1

  return (
    <div className="flex gap-6 items-stretch h-full max-md:flex-col max-md:items-center">
      {/* ── Tarot Card ── */}
      <div className="shrink-0 w-[280px] h-full">
        <div className="relative rounded-xl overflow-hidden bg-gradient-to-b from-stone-100 to-stone-200 shadow-[0_4px_30px_rgba(0,0,0,0.12)] border border-stone-300/50 h-full flex flex-col">
          {/* Decorative inner frame */}
          <div className="absolute inset-[8px] border border-amber-600/20 rounded-lg pointer-events-none z-10" />
          <div className="absolute inset-[12px] border border-amber-600/10 rounded-[6px] pointer-events-none z-10" />

          {/* Portrait */}
          <div className="flex-1 relative overflow-hidden">
            <span className="absolute inset-0 flex items-center justify-center font-narrative text-[100px] font-bold text-stone-300/30 z-[1]">
              {name[0]}
            </span>
            {imgUrl && (
              <img
                src={imgUrl}
                alt={name}
                className="absolute inset-0 w-full h-full object-cover object-top z-[2]"
                onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
              />
            )}
            <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-stone-900/40 to-transparent z-[3]" />
          </div>

          {/* Name plate */}
          <div className="relative bg-stone-800 px-4 py-3 text-center border-t border-amber-600/30 shrink-0">
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-16 h-px bg-gradient-to-r from-transparent via-amber-500/60 to-transparent" />
            <div className="flex items-baseline justify-center gap-2">
              <span className="font-display text-sm font-semibold text-stone-100 tracking-wider">
                {name}
              </span>
              {role && (
                <span className="font-data text-[9px] text-amber-400/70 tracking-[1.5px] uppercase">
                  {role}
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Slide Card ── */}
      <div className="flex-1 min-w-0 h-full bg-card/90 border border-border/30 rounded-xl flex flex-col overflow-hidden">
        {/* Card header — section tabs */}
        <div className="shrink-0 overflow-x-auto px-6 pt-5 pb-3 border-b border-border/20">
          <div className="flex items-center gap-3">
            {sections.map((s, i) => (
              <button
                key={s.key}
                onClick={() => setSectionIdx(i)}
                className={`font-data text-[11px] tracking-[1px] uppercase px-2 py-1 rounded transition-all whitespace-nowrap ${
                  i === sectionIdx
                    ? 'text-amber-600 bg-amber-500/10'
                    : 'text-muted-foreground hover:text-foreground/70'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {/* Card body — single section */}
        <div className="relative flex-1 overflow-y-auto px-6 py-5">
          {canEdit && (
            <button
              onClick={toggleEditing}
              className={`absolute top-5 right-6 font-data text-[11px] border rounded px-3 py-1 transition-all z-10 ${
                editing
                  ? 'text-amber-500 border-amber-500'
                  : 'text-muted-foreground border-border hover:text-amber-500 hover:border-amber-500'
              }`}
            >
              {editing ? <><Check size={12} className="inline mr-1" />{t('intro.done')}</> : <><PencilSimple size={12} className="inline mr-1" />{t('intro.edit')}</>}
            </button>
          )}
          {current.type === 'properties' ? (
            <PropertiesSection
              label={current.label}
              properties={current.value}
              editing={editing}
              fieldLabel={fieldLabel}
              onSave={(key, val) => updateAgentProperty(agent.id, { [key]: val })}
            />
          ) : (
            <CharacterSection
              label={current.label}
              value={current.value}
              hidden={current.hidden || false}
              editing={editing}
              onSave={(newVal) => updateCharacter(agent.id, { [current.key]: newVal })}
            />
          )}
        </div>

        {/* Card footer — prev/next navigation */}
        <div className="shrink-0 flex items-center justify-between px-6 py-3 border-t border-border/20">
          <button
            onClick={() => canPrev && setSectionIdx(sectionIdx - 1)}
            className={`flex items-center gap-1 font-data text-[11px] uppercase tracking-[1px] transition-colors ${
              canPrev ? 'text-muted-foreground hover:text-foreground cursor-pointer' : 'text-transparent cursor-default'
            }`}
          >
            <CaretLeft size={14} /> {canPrev ? sections[sectionIdx - 1].label : ''}
          </button>
          {/* Dots */}
          <div className="flex gap-1.5">
            {sections.map((_, i) => (
              <div
                key={i}
                className={`w-1.5 h-1.5 rounded-full transition-all cursor-pointer ${
                  i === sectionIdx ? 'bg-amber-500 scale-125' : 'bg-muted-foreground/30 hover:bg-muted-foreground/50'
                }`}
                onClick={() => setSectionIdx(i)}
              />
            ))}
          </div>
          <button
            onClick={() => canNext && setSectionIdx(sectionIdx + 1)}
            className={`flex items-center gap-1 font-data text-[11px] uppercase tracking-[1px] transition-colors ${
              canNext ? 'text-muted-foreground hover:text-foreground cursor-pointer' : 'text-transparent cursor-default'
            }`}
          >
            {canNext ? sections[sectionIdx + 1].label : ''} <CaretRight size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

/* ── Single character section (full-height content area) ── */

function CharacterSection({
  label,
  value,
  hidden,
  editing,
  onSave,
}: {
  label: string
  value: any
  hidden: boolean
  editing: boolean
  onSave: (v: any) => void
}) {
  const isList = Array.isArray(value)
  const [draft, setDraft] = useState(isList ? value.map(formatVal).join('\n') : formatVal(value))
  const draftRef = useRef(draft)
  draftRef.current = draft

  const valueKey = JSON.stringify(value)
  useEffect(() => {
    setDraft(isList ? value.map(formatVal).join('\n') : formatVal(value))
  }, [valueKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const prevEditing = useRef(editing)
  useEffect(() => {
    if (prevEditing.current && !editing) {
      const cur = draftRef.current
      const newVal = isList ? cur.split('\n').filter((s: string) => s.trim()) : cur
      onSave(newVal)
    }
    prevEditing.current = editing
  }, [editing]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      {/* Section title */}
      <div className="flex items-center gap-2 mb-4">
        <h3 className="font-display text-lg font-semibold capitalize">{label}</h3>
        {hidden && <Lock size={12} className="text-amber-500/60" />}
      </div>

      {editing ? (
        <Textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="font-narrative text-[14px] leading-8 text-muted-foreground bg-muted/30 border-border min-h-[200px] resize-y w-full"
          rows={isList ? (value as any[]).length + 2 : 8}
        />
      ) : isList ? (
        <ul className="list-none p-0 space-y-2">
          {(value as any[]).map((item, i) => (
            <li key={i} className="font-narrative text-[14px] leading-8 text-muted-foreground pl-4 relative before:content-['·'] before:absolute before:left-0 before:text-amber-500 before:font-bold">
              {formatVal(item)}
            </li>
          ))}
        </ul>
      ) : label.includes('\u8bf4\u8bdd') || label.includes('style') ? (
        <div className="font-narrative text-[14px] leading-8 text-muted-foreground/70 italic border-l-2 border-amber-500/30 pl-4">
          {formatVal(value)}
        </div>
      ) : (
        <div className="font-narrative text-[14px] leading-8 text-muted-foreground">
          {formatVal(value)}
        </div>
      )}
    </div>
  )
}

/* ── Properties section ── */

function PropertiesSection({
  label,
  properties,
  editing,
  fieldLabel,
  onSave,
}: {
  label: string
  properties: Record<string, any>
  editing: boolean
  fieldLabel: (key: string) => string
  onSave: (key: string, val: any) => void
}) {
  return (
    <div>
      <h3 className="font-display text-lg font-semibold mb-4">{label}</h3>
      <div className="space-y-3">
        {Object.entries(properties).map(([key, value]) => (
          <PropertyRow key={key} label={fieldLabel(key)} value={value} editing={editing} onSave={(v) => onSave(key, v)} />
        ))}
      </div>
    </div>
  )
}

function PropertyRow({
  label,
  value,
  editing,
  onSave,
}: {
  label: string
  value: any
  editing: boolean
  onSave: (v: any) => void
}) {
  const [draft, setDraft] = useState(String(value ?? ''))
  const draftRef = useRef(draft)
  draftRef.current = draft

  useEffect(() => { setDraft(String(value ?? '')) }, [value])

  const prevEditing = useRef(editing)
  useEffect(() => {
    if (prevEditing.current && !editing) {
      const parsed = typeof value === 'number' ? Number(draftRef.current) : draftRef.current
      if (parsed !== value) onSave(parsed)
    }
    prevEditing.current = editing
  }, [editing]) // eslint-disable-line react-hooks/exhaustive-deps

  if (typeof value === 'object' && value !== null) {
    return (
      <div className="flex items-center justify-between py-2 border-b border-border/10">
        <span className="font-data text-xs text-muted-foreground tracking-wider">{label}</span>
        <span className="font-data text-sm text-foreground/80">{JSON.stringify(value)}</span>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-between py-2 border-b border-border/10">
      <span className="font-data text-xs text-muted-foreground tracking-wider">{label}</span>
      {editing ? (
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          className="font-data text-sm h-7 w-32 px-2 bg-muted/30 border-border text-right"
        />
      ) : (
        <span className="font-data text-sm font-medium text-foreground/80">{String(value)}</span>
      )}
    </div>
  )
}
