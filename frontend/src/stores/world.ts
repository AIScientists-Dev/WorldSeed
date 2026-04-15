import { create } from 'zustand'
import { LS_CURRENT_RUN, LS_NARRATOR_STYLE, LS_NARRATOR_PROMPT } from '@/lib/constants'
import type { Entity, WorldEvent, Character } from '@/lib/types'
import type { NarratorStyle } from '@/lib/narrator'

interface WorldState {
  tick: number
  running: boolean
  worldStatus: string
  currentRunId: string
  scene: string | null
  uiConfigLoaded: boolean
  entities: Entity[]
  events: WorldEvent[]
  characters: Character[]
  actionDefs: Record<string, any>
  healthChecked: boolean
  gatewayStatus: { process_alive: boolean; connected: boolean; ws_connections: number }
  agentsInfo: { total: number; ready: string[]; pending: string[] }
  tokenCount: number
  viewingRunId: string
  pastRunsList: any[]
  prevEntityState: Record<string, any>
  deltas: Record<string, any>
  agentLastAction: Record<string, number>
  systemAgents: string[]
  narratorStyle: NarratorStyle
  narratorPrompt: string
}

interface WorldActions {
  set: (partial: Partial<WorldState>) => void
  setCurrentRunId: (runId: string) => void
  resetForNewRun: () => void
}

export const useWorldStore = create<WorldState & WorldActions>((set) => ({
  tick: 0,
  running: false,
  worldStatus: 'lobby',
  currentRunId: localStorage.getItem(LS_CURRENT_RUN) || '',
  scene: null,
  uiConfigLoaded: false,
  entities: [],
  events: [],
  characters: [],
  actionDefs: {},
  healthChecked: false,
  gatewayStatus: { process_alive: false, connected: false, ws_connections: 0 },
  agentsInfo: { total: 0, ready: [], pending: [] },
  tokenCount: 0,
  viewingRunId: '',
  pastRunsList: [],
  prevEntityState: {},
  deltas: {},
  agentLastAction: {},
  systemAgents: [],
  narratorStyle: (localStorage.getItem(LS_NARRATOR_STYLE) as NarratorStyle) || 'storyteller',
  narratorPrompt: localStorage.getItem(LS_NARRATOR_PROMPT) || '',

  set: (partial) => set(partial),

  setCurrentRunId: (runId) => {
    localStorage.setItem(LS_CURRENT_RUN, runId)
    set({ currentRunId: runId })
  },

  resetForNewRun: () => set({
    entities: [],
    events: [],
    prevEntityState: {},
    deltas: {},
    agentLastAction: {},
    tokenCount: 0,
  }),
}))

// --- Derived selectors (used via useMemo in components) ---

export function selectAgents(state: WorldState): Entity[] {
  return state.entities.filter(
    e => e.type === 'agent' && !state.systemAgents.includes(e.id)
  )
}

export function selectIsViewingHistory(state: WorldState): boolean {
  return !!(state.viewingRunId && state.viewingRunId !== state.currentRunId)
}

export function selectEffectiveRunId(state: WorldState): string {
  return state.viewingRunId || state.currentRunId
}
