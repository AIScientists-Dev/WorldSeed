import { LS_RIGHT_TAB } from '@/lib/constants'
import { create } from 'zustand'
import { FEEDBACK_TIMEOUT_MS } from '@/lib/constants'

interface EditingProp {
  entity: string | null
  key: string | null
  value: any
}

interface SavedProp {
  entity: string | null
  key: string | null
  ts: number
}

export type RightTab = 'stream' | 'inspector'
export type ChronicleMode = 'auto' | 'step'

interface UIState {
  openEntities: Record<string, boolean>
  whisperText: string
  gmResolveText: string
  gmFeedback: string
  showSettings: boolean
  eventFilter: string
  speed: number
  baseInterval: number
  editingProp: EditingProp
  savedProp: SavedProp
  rightTab: RightTab
  chronicleMode: ChronicleMode
  chronicleSheetOpen: boolean
}

interface UIActions {
  set: (partial: Partial<UIState>) => void
  toggleEntity: (id: string) => void
  toggleEventFilter: (type: string) => void
  toggleRightTab: () => void
  showFeedbackMsg: (msg: string) => void
}

export const useUIStore = create<UIState & UIActions>((set, get) => ({
  openEntities: {},
  whisperText: '',
  gmResolveText: '',
  gmFeedback: '',
  showSettings: false,
  eventFilter: '',
  speed: 1.0,
  baseInterval: 5.0,
  editingProp: { entity: null, key: null, value: null },
  savedProp: { entity: null, key: null, ts: 0 },
  rightTab: (localStorage.getItem(LS_RIGHT_TAB) === 'inspector' ? 'inspector' : 'stream') as RightTab,
  chronicleMode: (localStorage.getItem('ws-chronicle-mode') as ChronicleMode) || 'auto',
  chronicleSheetOpen: false,

  set: (partial) => set(partial),

  toggleEntity: (id) => set((s) => ({
    openEntities: { ...s.openEntities, [id]: s.openEntities[id] === false },
  })),

  toggleEventFilter: (type) => set((s) => ({
    eventFilter: s.eventFilter === type ? '' : type,
  })),

  toggleRightTab: () => {
    const next: RightTab = get().rightTab === 'inspector' ? 'stream' : 'inspector'
    set({ rightTab: next })
    localStorage.setItem(LS_RIGHT_TAB, next)
  },

  showFeedbackMsg: (msg) => {
    set({ gmFeedback: msg })
    setTimeout(() => { set({ gmFeedback: '' }) }, FEEDBACK_TIMEOUT_MS)
  },
}))
