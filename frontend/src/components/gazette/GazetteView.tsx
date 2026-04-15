import React, { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import i18n from '@/i18n'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft } from '@phosphor-icons/react'
import { Button } from '@/components/ui/button'
import { useGazetteStore, type GazetteContent, type GazetteAgent } from '@/stores/gazette'
import { uiConfig } from '@/lib/ui-config'

/** Hide parent element if image fails to load */
function hideOnError(e: React.SyntheticEvent<HTMLImageElement>) {
  const parent = e.currentTarget.parentElement
  if (parent) parent.style.display = 'none'
}

function resolveImageUrl(slot: string | null, assetPack: string): string {
  if (!slot || !assetPack) return ''
  const parts = slot.split('/')
  if (parts.length !== 2) return ''
  const [dir, name] = parts
  if (dir === 'scene') {
    return `/assets/scenes/${assetPack}/${name}.png`
  }
  return `/assets/scenes/${assetPack}/${dir}/${name}.png`
}

function avatarUrl(agentId: string, assetPack: string): string {
  if (!assetPack) return ''
  return `/assets/scenes/${assetPack}/agents/${agentId}.png`
}

const MAX_PROFILES = 8

export default function GazetteView() {
  const { t } = useTranslation()
  const { runId } = useParams<{ runId: string }>()
  const [searchParams] = useSearchParams()
  const gazetteId = searchParams.get('id')
  const navigate = useNavigate()

  const current = useGazetteStore(s => s.current)
  const currentId = useGazetteStore(s => s.currentId)
  const editions = useGazetteStore(s => s.editions)
  const fetchList = useGazetteStore(s => s.fetchList)
  const fetchGazette = useGazetteStore(s => s.fetchGazette)
  const status = useGazetteStore(s => s.status)
  const [assetPack, setAssetPack] = useState(uiConfig.assetPack || '')

  // Load ui config from gazette's scene_id
  useEffect(() => {
    if (!current) return
    if (uiConfig.loaded && uiConfig.assetPack) {
      setAssetPack(uiConfig.assetPack)
      return
    }
    uiConfig.load(current.scene_id).then((ok) => {
      if (ok) setAssetPack(uiConfig.assetPack)
    })
  }, [current?.scene_id])

  // Load gazette list on mount
  useEffect(() => {
    if (runId && status === 'idle') fetchList(runId)
  }, [runId, status, fetchList])

  // Load specific gazette once list is ready
  useEffect(() => {
    if (!runId || status !== 'loaded' || editions.length === 0) return
    const targetId = gazetteId || editions[0].id
    if (targetId !== currentId) fetchGazette(runId, targetId)
  }, [runId, gazetteId, status, editions, currentId, fetchGazette])

  const heroUrl = useMemo(
    () => assetPack ? `/assets/scenes/${assetPack}/scene.png` : '',
    [assetPack]
  )
  const date = useMemo(
    () => {
      const { language } = i18n
      return new Date().toLocaleDateString(language, {
        weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
      })
    },
    []
  )

  if (!current) {
    return (
      <div className="broadsheet" style={{ textAlign: 'center', paddingTop: '20vh' }}>
        <p className="text-muted-foreground text-sm">
          {status === 'idle' || status === 'loading' ? t('gazette.loading') : t('gazette.noGazette')}
        </p>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => navigate(`/run/${runId}/map`)}>
          <ArrowLeft size={14} /> {t('gazette.back')}
        </Button>
      </div>
    )
  }

  const g = current.gazette
  const gen = current.generation
  const agents = current.agents || []
  const leadImageUrl = resolveImageUrl(g.lead_story.image, assetPack)

  return (
    <div className="broadsheet">
      <Button variant="outline" size="sm" className="fixed top-4 left-4 z-10 shadow-sm" onClick={() => navigate(`/run/${runId}/map`)}>
        <ArrowLeft size={14} /> {t('gazette.back')}
      </Button>

      <header className="bs-masthead">
        <hr className="bs-masthead-rule top-outer" />
        <hr className="bs-masthead-rule top-inner" />
        <div className="bs-masthead-title">{g.edition_title}</div>
        <div className="bs-masthead-ornament">&loz; &loz; &loz;</div>
        <div className="bs-masthead-subtitle">
          Tick {current.tick_count || '?'} &middot; {t('gazette.finalEdition')}
        </div>
        {current.scene_description && (
          <div className="bs-masthead-scene">{current.scene_description}</div>
        )}
        <hr className="bs-masthead-rule bot-inner" />
        <hr className="bs-masthead-rule bot-outer" />
        <div className="bs-dateline">
          <span>WorldSeed</span>
          <span>{date}</span>
        </div>
      </header>

      {heroUrl && (
        <div className="bs-hero">
          <img src={heroUrl} alt="" onError={hideOnError} />
        </div>
      )}

      <div className="bs-breaking">
        <span className="flash">&#9679; {t('gazette.breaking')}</span>
        {g.breaking_banner}
      </div>

      <LeadStory story={g.lead_story} inlineImageUrl={leadImageUrl} />

      <div className="bs-pull-quote">
        <blockquote>&ldquo;{g.pull_quote}&rdquo;</blockquote>
      </div>

      <hr className="bs-rule thick" />

      <div className="bs-secondary-row">
        {g.secondary_stories.map((story, i) => (
          <SecondaryStory key={i} story={story} assetPack={assetPack} />
        ))}
      </div>

      <hr className="bs-rule" />

      <AgentProfiles agents={agents} assetPack={assetPack} />

      <div className="bs-rule ornamental">&sect; &nbsp; &sect; &nbsp; &sect;</div>

      <div className="bs-editorial-row">
        {g.editorials.map((ed, i) => (
          <Editorial key={i} editorial={ed} assetPack={assetPack} />
        ))}
      </div>

      <hr className="bs-rule" />

      <div className="bs-label">{t('gazette.eventTicker')}</div>
      {g.ticker.map((item, i) => (
        <div key={i} className="bs-ticker-item">
          <span className="bs-ticker-time">Tick {item.tick}</span>
          <span className="bs-ticker-text">{item.text}</span>
        </div>
      ))}

      <footer className="bs-footer">
        <div className="bs-footer-left">{g.edition_title} &middot; {t('gazette.publication')}</div>
        <div className="bs-footer-right">Tick {current.tick_count || '?'}</div>
      </footer>
    </div>
  )
}

/* ── Sub-components ── */

function LeadStory({ story, inlineImageUrl }: { story: GazetteContent['lead_story']; inlineImageUrl: string }) {
  const mid = Math.min(3, story.paragraphs.length - 1)
  return (
    <section>
      <h1 className="bs-lead-headline">{story.headline}</h1>
      <p className="bs-lead-deck">{story.deck}</p>
      <div className="bs-lead-body">
        {story.paragraphs.map((p, i) => (
          <React.Fragment key={i}>
            <p className={i === 0 ? 'bs-drop-cap' : undefined}>{p}</p>
            {i === mid && inlineImageUrl && (
              <div className="bs-inline-image">
                <img src={inlineImageUrl} alt="" onError={hideOnError} />
              </div>
            )}
          </React.Fragment>
        ))}
      </div>
    </section>
  )
}

function SecondaryStory({ story, assetPack }: { story: GazetteContent['secondary_stories'][0]; assetPack: string }) {
  const imgUrl = resolveImageUrl(story.image, assetPack)
  return (
    <article className="bs-secondary-story">
      {imgUrl && (
        <div className="bs-secondary-image">
          <img src={imgUrl} alt="" onError={hideOnError} />
        </div>
      )}
      <h2 className="bs-secondary-headline">{story.headline}</h2>
      <p className="bs-secondary-deck">{story.deck}</p>
      <div className="bs-secondary-body">
        {story.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
      </div>
    </article>
  )
}

function AgentProfiles({ agents, assetPack }: { agents: GazetteAgent[]; assetPack: string }) {
  const { t } = useTranslation()
  const colors = ['#5A6E5A', '#7A5C4F', '#4F5E7A', '#8A7A5A', '#6A5A7A', '#5A7A6E']
  const shown = agents.slice(0, MAX_PROFILES)
  const remaining = agents.length - shown.length
  const totalCards = shown.length + (remaining > 0 ? 1 : 0)
  const cols = Math.ceil(Math.sqrt(totalCards))
  return (
    <>
      <div className="bs-label">{t('gazette.dramatis')}</div>
      <div className="bs-profiles-grid" style={{ '--profile-cols': cols } as React.CSSProperties}>
        {shown.map((agent, i) => {
          const url = avatarUrl(agent.id, assetPack)
          return (
            <div key={i} className="bs-profile-card">
              {url ? (
                <img className="bs-profile-avatar-img" src={url} alt={agent.id} onError={hideOnError} />
              ) : (
                <div className="bs-profile-avatar" style={{ background: colors[i % colors.length] }}>
                  <span>{agent.id[0]}</span>
                </div>
              )}
              <div className="bs-profile-name">{agent.id}</div>
              <p className="bs-profile-bio">{agent.identity || ''}</p>
            </div>
          )
        })}
        {remaining > 0 && (
          <div className="bs-profile-card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontFamily: 'var(--caption)', fontSize: '0.7rem', color: 'var(--ink-faded)' }}>
              {t('gazette.moreCount', { count: remaining })}
            </span>
          </div>
        )}
      </div>
    </>
  )
}

function Editorial({ editorial, assetPack }: { editorial: GazetteContent['editorials'][0]; assetPack: string }) {
  const { t } = useTranslation()
  const url = avatarUrl(editorial.agent_id, assetPack)
  return (
    <section className="bs-editorial">
      <div className="bs-editorial-kicker">{t('gazette.editorial')}</div>
      {url && <img className="bs-editorial-avatar" src={url} alt={editorial.agent_id} onError={hideOnError} />}
      <h2 className="bs-editorial-headline">{editorial.headline}</h2>
      <p className="bs-editorial-author">{editorial.display_name}</p>
      <div className="bs-editorial-body">
        {editorial.paragraphs.map((p, i) => <p key={i}>{p}</p>)}
      </div>
      <p className="bs-editorial-sig">&mdash; {editorial.display_name}</p>
    </section>
  )
}
