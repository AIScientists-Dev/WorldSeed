import { create } from 'zustand'
import { LS_AGENT } from '@/lib/constants'
import type { AgentPerception } from '@/lib/types'

interface AgentState {
  selectedAgent: string | null
  agentLoading: boolean
  agentPerception: AgentPerception | null
  agentInbox: any
  agentLogs: any
  agentCharacter: any
  agentRuns: any[]
}

interface AgentActions {
  set: (partial: Partial<AgentState>) => void
  selectAgent: (id: string | null) => void
}

export const useAgentStore = create<AgentState & AgentActions>((set) => ({
  selectedAgent: localStorage.getItem(LS_AGENT) || null,
  agentLoading: false,
  agentPerception: null,
  agentInbox: null,
  agentLogs: null,
  agentCharacter: null,
  agentRuns: [],

  set: (partial) => set(partial),

  selectAgent: (id) => {
    if (id) localStorage.setItem(LS_AGENT, id)
    else localStorage.removeItem(LS_AGENT)
    if (!id) {
      set({
        selectedAgent: null,
        agentPerception: null,
        agentInbox: null,
        agentLogs: null,
        agentCharacter: null,
        agentRuns: [],
        agentLoading: false,
      })
    } else {
      set({ selectedAgent: id })
    }
  },
}))
