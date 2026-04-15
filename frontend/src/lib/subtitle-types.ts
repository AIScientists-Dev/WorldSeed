/* WorldSeed — Subtitle system types.
 *
 * Data pipeline: StreamRecord → RawCue → FormattedCue → MeasuredCue → store
 * Each stage adds information; nothing is mutated after creation.
 */

/** Output of classifier: raw event data, no display formatting. */
export interface RawCue {
  kind: 'action' | 'speech' | 'description' | 'narrative'
  agentId: string
  actionType: string
  params: Record<string, unknown>
  freeText: string | null
  narrative: string | null
  tick: number
}

/** Output of formatter: display-ready text, no measurement. */
export interface FormattedCue extends RawCue {
  id: string
  displayText: string
}

/** Output of measure: ready to enqueue into store. */
export interface MeasuredCue extends FormattedCue {
  /** Pure text width from pretext (widest line, shrink-wrapped). No chrome. */
  textW: number
  /** Pure text height from pretext (lineCount × lineHeight). No chrome. */
  textH: number
  /** Narrative only: pretext line-break data for line-by-line reveal. */
  lines?: Array<{ text: string; width: number }>
}

/** Timing constants — all in one place for tuning. */
export const SUBTITLE_TIMING = {
  /** Chip hold time before fading (ms) */
  chipHoldMs: 1200,
  /** Speech hold time after typewriter finishes (ms) */
  speechHoldMs: 800,
  /** Narrative hold time after typewriter finishes (ms) */
  narrativeHoldMs: 1200,
  /** Narrative bar appear duration (ms, CSS transition) */
  narrativeBarAppearMs: 400,
  /** Narrative pause after bar appears, before typewriter starts (ms) */
  narrativePauseMs: 350,
  /** Speech typewriter speed — Latin text (ms per character) */
  speechMsPerChar: 35,
  /** Speech typewriter speed — CJK text (~9 CPS, matches subtitle reading standards) */
  cjkSpeechMsPerChar: 110,
  /** Narrative typewriter speed — Latin text (ms per character) */
  narrativeMsPerChar: 60,
  /** Narrative typewriter speed — CJK text */
  cjkNarrativeMsPerChar: 90,
  /** Punctuation pause multiplier */
  punctMultiplier: 4,
  /** Gap between cues during sequential playback (ms) */
  interCueMs: 100,
  /** Delay after mouse leaves narrative bar before advancing (ms) */
  narrativeMouseLeaveMs: 600,
  /** Bubble max text width (px) */
  bubbleMaxTextW: 260,
  /** Narrative max text width (px) */
  narrativeMaxW: 520,
  /** Live mode speed-up thresholds: [queueDepth, speedMultiplier] */
  liveSpeedUp: [
    [10, 3.0],
    [7, 2.0],
    [4, 1.5],
  ] as const,
} as const

const CJK_RE = /[\u4E00-\u9FFF\u3400-\u4DBF]/

/** Return the appropriate ms-per-char for a text string (CJK-aware). */
export function speechMsPerChar(text: string): number {
  return CJK_RE.test(text) ? SUBTITLE_TIMING.cjkSpeechMsPerChar : SUBTITLE_TIMING.speechMsPerChar
}

/** Return the appropriate narrative ms-per-char for a text string (CJK-aware). */
export function narrativeMsPerChar(text: string): number {
  return CJK_RE.test(text) ? SUBTITLE_TIMING.cjkNarrativeMsPerChar : SUBTITLE_TIMING.narrativeMsPerChar
}
