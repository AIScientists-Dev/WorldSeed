import { create } from 'zustand'
import { apiPost } from '@/lib/api'

export interface GazetteEstimate {
  input_tokens: number
  estimated_output_tokens: number
  estimated_cost_usd: number
  model: string
}

export interface GazetteStory {
  headline: string
  deck: string
  paragraphs: string[]
  image: string | null
}

export interface GazetteEditorial {
  agent_id: string
  display_name: string
  headline: string
  paragraphs: string[]
}

export interface GazetteTicker {
  tick: number
  text: string
}

export interface GazetteContent {
  edition_title: string
  breaking_banner: string
  lead_story: GazetteStory
  secondary_stories: GazetteStory[]
  editorials: GazetteEditorial[]
  ticker: GazetteTicker[]
  pull_quote: string
}

export interface GazetteAgent {
  id: string
  identity: string
  personality: string
}

export interface GazetteResult {
  run_id: string
  scene_id: string
  scene_description: string
  tick_count: number
  language: string
  generation: {
    model: string
    elapsed_s: number
    tokens_in: number
    tokens_out: number
    cost_usd: number
    created_at?: string
  }
  gazette: GazetteContent
  agents: GazetteAgent[]
}

export interface GazetteSummary {
  id: string
  edition_title: string
  language: string
  model: string
  cost_usd: number
  created_at: string
}

type GazetteStatus = 'idle' | 'loading' | 'loaded' | 'generating' | 'error' | 'no_model'

const LS_GAZETTE_LANG = 'worldseed:gazette-language'

interface GazetteState {
  status: GazetteStatus
  // List of all gazettes for this run
  editions: GazetteSummary[]
  // Currently viewed gazette (full content)
  current: GazetteResult | null
  currentId: string | null
  // Estimate for generating a new one
  estimate: GazetteEstimate | null
  noModel: boolean
  error: string | null
  generatingStartedAt: number | null
  language: string
}

interface GazetteActions {
  fetchList: (runId: string) => Promise<void>
  fetchGazette: (runId: string, gazetteId: string) => Promise<void>
  generate: (runId: string) => Promise<void>
  setLanguage: (lang: string) => void
  reset: () => void
}

const INITIAL: GazetteState = {
  status: 'idle',
  editions: [],
  current: null,
  currentId: null,
  estimate: null,
  noModel: false,
  error: null,
  generatingStartedAt: null,
  language: localStorage.getItem(LS_GAZETTE_LANG) || 'English',
}

export const useGazetteStore = create<GazetteState & GazetteActions>((set, get) => ({
  ...INITIAL,

  fetchList: async (runId: string) => {
    set({ status: 'loading', error: null })
    try {
      const r = await fetch(`/api/runs/${runId}/gazette`)
      if (!r.ok) {
        const body = await r.json().catch(() => ({ detail: `HTTP ${r.status}` }))
        set({ status: 'error', error: body.detail || `HTTP ${r.status}` })
        return
      }
      const data = await r.json()
      set({
        status: 'loaded',
        editions: data.gazettes || [],
        estimate: data.estimate || null,
        noModel: data.no_model || false,
      })
    } catch (e: any) {
      set({ status: 'error', error: e.message || 'Network error' })
    }
  },

  fetchGazette: async (runId: string, gazetteId: string) => {
    try {
      const r = await fetch(`/api/runs/${runId}/gazette/${gazetteId}`)
      if (!r.ok) return
      const data = await r.json()
      set({ current: data.gazette, currentId: gazetteId })
    } catch {
      // silent — gazette view will show fallback
    }
  },

  generate: async (runId: string) => {
    const lang = get().language
    set({ status: 'generating', generatingStartedAt: Date.now(), error: null })
    const result = await apiPost(`/api/runs/${runId}/gazette`, { language: lang })
    if (result.ok && result.data.gazette) {
      set({
        status: 'loaded',
        current: result.data.gazette,
        currentId: result.data.gazette_id,
        generatingStartedAt: null,
      })
      // Refresh the list
      get().fetchList(runId)
    } else {
      set({
        status: 'error',
        error: result.data?.detail || 'Generation failed',
        generatingStartedAt: null,
      })
    }
  },

  setLanguage: (lang: string) => {
    localStorage.setItem(LS_GAZETTE_LANG, lang)
    set({ language: lang })
  },

  reset: () => set({ ...INITIAL, language: get().language }),
}))
