import { create } from 'zustand'
import type { StreamRecord } from '@/lib/types'
import { HIDDEN_KINDS, DIGEST_HIDDEN_KINDS, STORY_HIDDEN_KINDS, KIND_DISPLAY, AGENT_NOOP_REPLIES } from '@/lib/stream-format'
import { LS_STREAM_VIEW } from '@/lib/constants'

export interface AgentText {
  agent_id: string
  text: string
  ts: string
  tool_calls: { action: string; params: Record<string, unknown> }[]
}

function toMs(ts: string): number {
  return new Date(ts).getTime() || 0
}

export type StreamViewMode = 'chapters' | 'all'
export type StreamSubFilter = 'digest' | 'story' | 'all'

interface StreamState {
  streamRecords: StreamRecord[]
  streamConnected: boolean
  streamViewMode: StreamViewMode
  streamSubFilter: StreamSubFilter
  streamKindFilter: string
  streamHiddenKinds: string[]
  streamAgentFilter: string
  agentTexts: AgentText[]
  agentTextsRunId: string
}

interface StreamActions {
  set: (partial: Partial<StreamState>) => void
  pushRecord: (rec: any) => void
  resetForNewRun: () => void
  toggleHiddenKind: (kind: string) => void
  setViewMode: (mode: StreamViewMode) => void
  setSubFilter: (filter: StreamSubFilter) => void
  setAgentFilter: (agent: string) => void
}

export const useStreamStore = create<StreamState & StreamActions>((set, get) => ({
  streamRecords: [],
  streamConnected: false,
  streamViewMode: (['chapters', 'all'].includes(localStorage.getItem(LS_STREAM_VIEW) || '') ? localStorage.getItem(LS_STREAM_VIEW) : 'all') as StreamViewMode,
  streamSubFilter: (localStorage.getItem('ws-stream-subfilter') as StreamSubFilter) || 'story',
  streamKindFilter: '',
  streamHiddenKinds: [],
  streamAgentFilter: '',
  agentTexts: [],
  agentTextsRunId: '',

  set: (partial) => set(partial),

  pushRecord: (rec) => set((s) => ({
    streamRecords: [...s.streamRecords, rec],
  })),

  resetForNewRun: () => set({ streamRecords: [], streamConnected: false }),

  toggleHiddenKind: (kind) => set((s) => {
    const has = s.streamHiddenKinds.includes(kind)
    return { streamHiddenKinds: has ? s.streamHiddenKinds.filter(k => k !== kind) : [...s.streamHiddenKinds, kind] }
  }),

  setViewMode: (mode) => {
    localStorage.setItem(LS_STREAM_VIEW, mode)
    set({ streamViewMode: mode })
  },

  setSubFilter: (filter) => {
    localStorage.setItem('ws-stream-subfilter', filter)
    set({ streamSubFilter: filter })
  },

  setAgentFilter: (agent) => set({ streamAgentFilter: agent }),
}))

// --- Derived data (use via useMemo in components) ---

export function computeStreamFilteredRecords(
  streamRecords: StreamRecord[],
  streamKindFilter: string,
  agentTexts: AgentText[],
  viewMode: StreamViewMode = 'all',
  agentFilter: string = '',
  hiddenKinds: string[] = [],
  subFilter: StreamSubFilter = 'story',
  systemAgents: string[] = [],
): StreamRecord[] {
  let list = streamRecords

  // Sub-filter within "all" tab: digest/story/all control what's hidden
  const baseHidden = subFilter === 'digest' ? DIGEST_HIDDEN_KINDS
    : subFilter === 'story' ? STORY_HIDDEN_KINDS
    : HIDDEN_KINDS

  // Exclusive kind filter (when a specific kind chip is active)
  if (streamKindFilter) {
    list = list.filter(r => (KIND_DISPLAY[r.kind] || r.kind) === streamKindFilter)
  } else {
    // Base hidden kinds from sub-filter
    list = list.filter(r => !baseHidden.has(r.kind))
    list = list.filter(r => !(r.kind === 'event' && (r as any).scope === 'admin'))
    // Story/digest: hide failed actions (engine rejections, not narrative)
    if (subFilter !== 'all') {
      list = list.filter(r => !(r.kind === 'action' && (r as any).success === false))
      // Hide records with no readable content (empty consequence ticks, etc.)
      list = list.filter(r => {
        if (r.kind === 'register') return true // always show join
        const detail = (r as any).detail || (r as any).narrative || (r as any).text || ''
        const message = (r as any).params?.message || ''
        return !!(detail || message || (r.kind === 'action' && r.agent_id))
      })
    }

    // User-toggled hidden kinds (Full mode combo filter)
    if (hiddenKinds.length > 0) {
      const userHidden = new Set(hiddenKinds)
      list = list.filter(r => !userHidden.has(KIND_DISPLAY[r.kind] || r.kind))
    }

    // No dedup needed: Digest/Story only show events (actions filtered by HIDDEN_KINDS).
    // All view shows both but they serve different purposes (event=narrative, action=debug).
  }

  // Agent filter — match agent_id or entity_id (for gm_set etc.)
  if (agentFilter) {
    list = list.filter(r => {
      const rid = (r as any).agent_id || (r as any).entity_id || ''
      return rid === agentFilter
    })
  }

  const showAgentText = !baseHidden.has('agent_text') && !hiddenKinds.includes('agent_text')
  if (agentTexts.length && (!streamKindFilter || streamKindFilter === 'agent_text') && showAgentText) {
    const tickTimes: { tick: number; ms: number }[] = []
    let prevTick: number | null = null
    for (const r of list) {
      if (r.tick !== prevTick && r.ts) {
        tickTimes.push({ tick: r.tick as number, ms: toMs(r.ts as string) })
        prevTick = r.tick
      }
    }
    const textRecords = agentTexts
      .filter(at => !agentFilter || at.agent_id === agentFilter)
      .filter(at => !AGENT_NOOP_REPLIES.has(at.text?.trim() ?? ''))
      .map(at => {
        const atMs = toMs(at.ts)
        let bestTick = tickTimes.length ? tickTimes[0].tick : 0
        for (const tt of tickTimes) {
          if (tt.ms <= atMs) bestTick = tt.tick
          else break
        }
        return {
          kind: 'agent_text',
          tick: bestTick,
          ts: at.ts,
          agent_id: at.agent_id,
          text: at.text,
          tool_calls: at.tool_calls || [],
        } as StreamRecord
      })
    list = [...list, ...textRecords]
    list.sort((a, b) => toMs((a.ts as string) || '0') - toMs((b.ts as string) || '0'))
  }

  // System agents (narrator etc.) have dedicated UI — hide from story/digest.
  if (systemAgents.length && subFilter !== 'all') {
    const sysSet = new Set(systemAgents)
    list = list.filter(r => !sysSet.has((r as any).agent_id || '') && !sysSet.has((r as any).source || ''))
  }

  return list
}

export function computeStreamGroups(records: StreamRecord[]): { tick: number; records: StreamRecord[] }[] {
  const groups: { tick: number; records: StreamRecord[] }[] = []
  let curTick: number | null = null
  let curGroup: { tick: number; records: StreamRecord[] } | null = null
  for (const rec of records) {
    if (rec.tick !== curTick) {
      curGroup = { tick: rec.tick, records: [] }
      groups.push(curGroup)
      curTick = rec.tick
    }
    curGroup!.records.push(rec)
  }
  return groups
}
