/* WorldSeed — Intro page store
 *
 * Single data source: /api/runs/{runId}/intro
 * Mode determined by: is_live flag from backend + worldStatus from world store
 */
import { create } from 'zustand'
import { apiFetch, apiPatch } from '@/lib/api'
import { uiConfig } from '@/lib/ui-config'
import { useWorldStore } from '@/stores/world'

export const INTRO_ERROR = {
  NO_SERVER: 'no_server',
  NO_WORLD: 'no_world',
} as const

export interface IntroAgent {
  id: string
  character: Record<string, any>
  properties: Record<string, any>
}

export interface IntroEntity {
  id: string
  type: string
  [key: string]: any
}

interface IntroState {
  phase: 0 | 1 | 2
  mode: 'prelaunch' | 'reference'
  scene: { id: string; description: string } | null
  entities: IntroEntity[]
  agents: IntroAgent[]
  selectedAgentIdx: number
  editing: boolean
  typewriterDone: boolean
  loading: boolean
  error: string

  fetchIntroData: (runId?: string) => Promise<void>
  setPhase: (p: 0 | 1 | 2) => void
  selectAgent: (idx: number) => void
  toggleEditing: () => void
  finishTypewriter: () => void
  updateCharacter: (agentId: string, overrides: Record<string, any>) => Promise<void>
  updateAgentProperty: (agentId: string, updates: Record<string, any>) => Promise<void>
  updateEntityProperty: (entityId: string, updates: Record<string, any>) => Promise<void>
}

export const useIntroStore = create<IntroState>((set, get) => ({
  phase: 0,
  mode: 'prelaunch',
  scene: null,
  entities: [],
  agents: [],
  selectedAgentIdx: 0,
  editing: false,
  typewriterDone: false,
  loading: false,
  error: '',

  fetchIntroData: async (runId?: string) => {
    set({ loading: true, error: '', typewriterDone: false, phase: 0, selectedAgentIdx: 0, editing: false })

    if (!runId) {
      set({ error: INTRO_ERROR.NO_WORLD, loading: false })
      return
    }

    // Single endpoint — works for both live and historical runs
    const data = await apiFetch(`/api/runs/${runId}/intro`)

    if (!data) {
      set({ error: INTRO_ERROR.NO_SERVER, loading: false })
      return
    }

    if (!data.scene) {
      set({ error: INTRO_ERROR.NO_WORLD, loading: false })
      return
    }

    if (data.scene.id) await uiConfig.load(data.scene.id)

    // Mode: prelaunch if this is the live run AND world hasn't fully started yet
    const ws = useWorldStore.getState()
    const isCurrentRun = data.is_live && runId === ws.currentRunId
    const mode = isCurrentRun ? 'prelaunch' : 'reference'

    set({
      mode,
      scene: data.scene,
      entities: data.entities || [],
      agents: data.agents || [],
      loading: false,
    })
  },

  setPhase: (p) => set({ phase: p, editing: false }),

  selectAgent: (idx) => set({ selectedAgentIdx: idx, editing: false }),

  toggleEditing: () => set({ editing: !get().editing }),

  finishTypewriter: () => set({ typewriterDone: true }),

  updateCharacter: async (agentId, overrides) => {
    const result = await apiPatch(`/api/agents/${agentId}/character`, { overrides })
    if (result.ok) {
      set({
        agents: get().agents.map((a) =>
          a.id === agentId ? { ...a, character: result.data.character } : a,
        ),
      })
    }
  },

  updateAgentProperty: async (agentId, updates) => {
    const result = await apiPatch(`/api/agents/${agentId}/properties`, { updates })
    if (result.ok) {
      set({
        agents: get().agents.map((a) =>
          a.id === agentId ? { ...a, properties: result.data.properties } : a,
        ),
      })
    }
  },

  updateEntityProperty: async (entityId, updates) => {
    const result = await apiPatch(`/api/entities/${entityId}/properties`, { updates })
    if (result.ok) {
      set({
        entities: get().entities.map((e) =>
          e.id === entityId ? { ...e, ...result.data.properties, id: entityId, type: e.type } : e,
        ),
      })
    }
  },
}))
