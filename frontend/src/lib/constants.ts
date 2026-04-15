/* WorldSeed — Shared constants (single source of truth) */

// localStorage keys
export const LS_AGENT = 'ws-agent'
export const LS_CURRENT_RUN = 'ws-current-run'

// localStorage keys — panel state
export const LS_THINKING_W = 'ws-thinking-w'
export const LS_RIGHT_TAB = 'ws-right-tab'
export const LS_STREAM_VIEW = 'ws-stream-view'
export const LS_DM_MODEL = 'ws-dm-model'
export const LS_NARRATOR_STYLE = 'ws-narrator-style'
export const LS_NARRATOR_PROMPT = 'ws-narrator-prompt'

// Visual
export const GRAIN_BG = `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`

// Timing (milliseconds)
export const FEEDBACK_TIMEOUT_MS = 3000
export const SAVED_PROP_TIMEOUT_MS = 1500
export const POLL_WORLD_INTERVAL_MS = 5000
export const POLL_AGENT_INTERVAL_MS = 10000
