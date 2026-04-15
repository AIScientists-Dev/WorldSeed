/* WorldSeed — UI Config loader: scene type registry + rule matching.
 *
 * Reactive singleton. Zero hardcoded entity types or property names.
 * .ui.json files are fully self-contained — all rules and events inline.
 *
 * DEFAULT_CONFIG is degraded mode: minimal rules for when no .ui.json exists.
 * Production scenes MUST have a .ui.json file.
 */

export interface SceneType {
  role: 'container' | 'agent' | 'item' | 'free' | 'hidden'
  assetDir: string
}

export const SCENE_TYPES: Record<string, SceneType> = {
  zone:     { role: 'container', assetDir: 'entities' },
  deck:     { role: 'container', assetDir: 'entities' },
  card:     { role: 'item',      assetDir: 'entities' },
  gauge:    { role: 'item',      assetDir: 'entities' },
  avatar:   { role: 'agent',     assetDir: 'agents'   },
  fallback: { role: 'free',      assetDir: 'entities' },
  hidden:   { role: 'hidden',    assetDir: ''         },
}

export interface UIRule {
  match?: { id?: string; type?: string }
  scene?: string
  bind?: Record<string, any>
}

export interface UIEventStyle {
  match: string
  bubble?: string
  effect?: string
}

interface UIConfig {
  asset_pack?: string
  rules?: UIRule[]
  events?: UIEventStyle[]
  event_defaults?: { bubble?: string; effect?: string }
  layout?: Record<string, { x: number; y: number; w: number; h: number; rotation?: number; z?: number }>
}

/** Degraded mode — used ONLY when no .ui.json exists.
 *  Agents get avatar with locate_by; everything else gets a card. */
const DEFAULT_CONFIG: UIConfig = {
  event_defaults: { bubble: 'action' },
  rules: [
    { match: { type: 'agent' }, scene: 'avatar', bind: { locate_by: 'location' } },
    { match: {}, scene: 'card', bind: {} },
  ],
  events: [],
}

// ── Singleton ──

export const uiConfig = {
  rules: [] as UIRule[],
  events: [] as UIEventStyle[],
  eventDefaults: {} as { bubble?: string; effect?: string },
  layout: {} as Record<string, { x: number; y: number; w: number; h: number; rotation?: number; z?: number }>,
  assetPack: '',
  loaded: false,

  async load(sceneId: string): Promise<boolean> {
    if (!sceneId) return false
    try {
      const resp = await fetch(`/configs/${sceneId}.ui.json?_=${Date.now()}`)
      const ct = resp.headers.get('content-type') || ''
      const config: UIConfig = (resp.ok && ct.includes('json'))
        ? await resp.json()
        : DEFAULT_CONFIG
      this.rules = config.rules || []
      this.events = config.events || []
      this.eventDefaults = config.event_defaults || {}
      this.layout = config.layout || {}
      this.assetPack = config.asset_pack || ''
      this.loaded = true
      return true
    } catch {
      this.rules = [...(DEFAULT_CONFIG.rules || [])]
      this.events = [...(DEFAULT_CONFIG.events || [])]
      this.eventDefaults = { ...(DEFAULT_CONFIG.event_defaults || {}) }
      this.layout = {}
      this.assetPack = ''
      this.loaded = true
      return true
    }
  },

  findRule(entity: any): UIRule {
    const eid = String(entity.id || '')
    const etype = String(entity.type || '')
    for (const rule of this.rules) {
      const m = rule.match || {}
      if (m.id && String(m.id) !== eid) continue
      if (m.type && String(m.type) !== etype) continue
      return rule
    }
    return {}
  },

  getBind(entity: any): Record<string, any> {
    return this.findRule(entity).bind || {}
  },

  getSceneName(entity: any): string {
    const rule = this.findRule(entity)
    return rule.scene ? String(rule.scene) : 'fallback'
  },

  getSceneType(entity: any): SceneType {
    const name = this.getSceneName(entity)
    return SCENE_TYPES[name] || SCENE_TYPES.fallback
  },

  getEventStyle(eventType: string): string {
    for (const ev of this.events) {
      if (String(ev.match || '') === eventType)
        return String(ev.bubble || this.eventDefaults.bubble || '')
    }
    return String(this.eventDefaults.bubble || '')
  },

  getEventEffect(eventType: string): string {
    for (const ev of this.events) {
      if (String(ev.match || '') === eventType)
        return String(ev.effect || this.eventDefaults.effect || '')
    }
    return String(this.eventDefaults.effect || '')
  },

  assetUrl(entity: any): string {
    if (!this.assetPack || !entity) return ''
    const st = this.getSceneType(entity)
    const dir = st.assetDir || 'entities'
    return `/assets/scenes/${this.assetPack}/${dir}/${entity.id}.png`
  },

  vignetteUrl(entity: any): string {
    if (!this.assetPack || !entity) return ''
    return `/assets/scenes/${this.assetPack}/entities/${entity.id}.png`
  },

  avatarUrl(entity: any): string {
    if (!this.assetPack || !entity) return ''
    return `/assets/scenes/${this.assetPack}/agents/${entity.id}.png`
  },
}
