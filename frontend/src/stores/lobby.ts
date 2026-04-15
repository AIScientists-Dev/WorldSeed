import { create } from 'zustand'
import { LS_DM_MODEL, LS_NARRATOR_STYLE, LS_NARRATOR_PROMPT } from '@/lib/constants'
import type { NarratorStyle } from '@/lib/narrator'

export interface ModelEntry {
  id: string
}

export interface ProviderGroup {
  provider: string
  models: ModelEntry[]
}

interface LobbyState {
  configs: any[]
  configPath: string
  dmModel: string
  dmFallback: string
  maxTicks: number
  timeoutMin: number
  maxDmCalls: number
  tickInterval: number
  narratorStyle: NarratorStyle
  narratorPrompt: string
  starting: boolean
  error: string
  pastRuns: any[]
  serverReachable: boolean
  availableModels: ProviderGroup[]
  modelsLoaded: boolean
  customModel: boolean
}

export const useLobbyStore = create<LobbyState>(() => ({
  configs: [],
  configPath: '',
  dmModel: localStorage.getItem(LS_DM_MODEL) || '',
  dmFallback: '',
  maxTicks: 200,
  timeoutMin: 10,
  maxDmCalls: 50,
  tickInterval: 5,
  narratorStyle: (localStorage.getItem(LS_NARRATOR_STYLE) as NarratorStyle) || 'storyteller',
  narratorPrompt: localStorage.getItem(LS_NARRATOR_PROMPT) || '',
  starting: false,
  error: '',
  pastRuns: [],
  serverReachable: false,
  availableModels: [],
  modelsLoaded: false,
  customModel: false,
}))
