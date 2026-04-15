import { create } from 'zustand'

interface AppState {
  appMode: 'loading' | 'lobby' | 'dashboard'
  lastError: string
  setError: (msg: string) => void
}

export const useAppStore = create<AppState>((set) => ({
  appMode: 'loading',
  lastError: '',
  setError: (msg) => set({ lastError: msg }),
}))
