/* WorldSeed — Subtitle measurement: FormattedCue → MeasuredCue.
 *
 * Uses pretext to pre-compute text dimensions without DOM rendering.
 * This is the ONLY file that calls pretext — all other modules receive
 * pre-measured data.
 *
 * MeasuredCue stores PURE TEXT dimensions (textW, textH) — no chrome
 * (avatar, padding, gap). Rendering components apply chrome via CSS.
 */

import { layout, prepareWithSegments, layoutWithLines, walkLineRanges } from '@chenglou/pretext'
import type { StreamRecord } from '@/lib/types'
import type { FormattedCue, MeasuredCue } from './subtitle-types'
import { SUBTITLE_TIMING } from './subtitle-types'
import { classify } from './subtitle-classifier'
import { format } from './subtitle-format'

// Font strings must match rendered CSS exactly for accurate measurement.
// Variable variants listed first to match @fontsource loading order in globals.css.
// Line heights match Tailwind classes: leading-snug (1.375), leading-relaxed (1.625).
// Entity card fonts — match worldview.css .entity-card-fallback / .entity-card-value
const FONT_ENTITY_FALLBACK = '10px "Source Serif 4 Variable", "Source Serif 4", "Noto Serif SC", serif'
const FONT_ENTITY_FALLBACK_COMPACT = '8px "Source Serif 4 Variable", "Source Serif 4", "Noto Serif SC", serif'
const FONT_ENTITY_VALUE = '9px "IBM Plex Mono", monospace'
const ENTITY_CARD_INNER_W = 67 // 82px max-width - 10px padding (2*5) - 5px border (2*2.5)
const ENTITY_CARD_COMPACT_INNER_W = 45 // 56px max-width - 8px padding (2*4) - 3px border (2*1.5)
const ENTITY_CARD_PAD = 10 + 5 // padding (3+5)*2 sides ≈ 10 + border 2.5*2 ≈ 5

/** Measure single-line text width in pixels using pretext. */
export function measureTextWidth(text: string, font: string): number {
  if (!text) return 0
  let w = 0
  const p = prepareWithSegments(text, font)
  walkLineRanges(p, Infinity, (line) => { w = line.width })
  return Math.ceil(w)
}

/** Measure the card width needed for an entity name. Returns total card px including padding/border. */
export function measureEntityCardWidth(name: string, compact: boolean): number {
  const font = compact ? FONT_ENTITY_FALLBACK_COMPACT : FONT_ENTITY_FALLBACK
  const textW = measureTextWidth(name, font)
  return textW + ENTITY_CARD_PAD
}

const FONT_CHIP = '13px "IBM Plex Sans Variable", "IBM Plex Sans", sans-serif'
const FONT_SPEECH = '14px "Source Serif 4 Variable", "Source Serif 4", "Noto Serif SC", serif'
const FONT_NARRATIVE = '15px "Source Serif 4 Variable", "Source Serif 4", "Noto Serif SC", serif'

const LH_CHIP = 18    // 13px × leading-snug(1.375) ≈ 17.9 → 18
const LH_SPEECH = 20  // 14px × leading-snug(1.375) ≈ 19.3 → 20
const LH_NARRATIVE = 24 // 15px × leading-relaxed(1.625) ≈ 24.4 → 24

const MAX_SPEECH_LINES = 5

/** Truncate text to fit within maxLines using pretext line breaks. */
function truncateByLines(
  text: string, font: string, maxWidth: number, lineHeight: number, maxLines: number,
): string {
  const p = prepareWithSegments(text, font)
  const r = layoutWithLines(p, maxWidth, lineHeight)
  if (r.lineCount <= maxLines) return text
  const kept = r.lines.slice(0, maxLines).map(l => l.text).join('')
  return kept.trimEnd() + '...'
}

/** Truncate text to fit a pixel width. Returns { text, truncated }. */
function truncateToWidth(
  text: string, font: string, maxWidth: number,
): { text: string; truncated: boolean } {
  if (!text) return { text: '', truncated: false }
  const p = prepareWithSegments(text, font)
  const r = layout(p, maxWidth, 999) // single-line: huge lineHeight
  if (r.lineCount <= 1) return { text, truncated: false }
  // Text wraps → binary search for the longest prefix that fits one line
  let lo = 0, hi = text.length
  while (lo < hi) {
    const mid = (lo + hi + 1) >>> 1
    const sub = text.slice(0, mid) + '…'
    const pr = prepareWithSegments(sub, font)
    const lr = layout(pr, maxWidth, 999)
    if (lr.lineCount <= 1) lo = mid
    else hi = mid - 1
  }
  return { text: text.slice(0, lo) + '…', truncated: true }
}

/** Truncate entity card text. Used by EntityCard for fallback name and value. */
export function truncateEntityText(
  text: string, kind: 'fallback' | 'value', compact?: boolean,
): { text: string; truncated: boolean } {
  const font = kind === 'fallback'
    ? (compact ? FONT_ENTITY_FALLBACK_COMPACT : FONT_ENTITY_FALLBACK)
    : FONT_ENTITY_VALUE
  const maxW = compact ? ENTITY_CARD_COMPACT_INNER_W : ENTITY_CARD_INNER_W
  return truncateToWidth(text, font, maxW)
}

/**
 * Measure a formatted cue using pretext.
 * Returns pure text dimensions — no padding, avatar, or gap included.
 */
export function measure(formatted: FormattedCue): MeasuredCue {
  const { bubbleMaxTextW, narrativeMaxW } = SUBTITLE_TIMING

  if (formatted.kind === 'narrative') {
    const p = prepareWithSegments(formatted.displayText, FONT_NARRATIVE)
    const r = layoutWithLines(p, narrativeMaxW, LH_NARRATIVE)
    return {
      ...formatted,
      textW: narrativeMaxW,
      textH: r.height,
      lines: r.lines.map(l => ({ text: l.text, width: l.width })),
    }
  }

  if (formatted.kind === 'speech' || formatted.kind === 'description') {
    const truncated = truncateByLines(
      formatted.displayText, FONT_SPEECH, bubbleMaxTextW, LH_SPEECH, MAX_SPEECH_LINES,
    )
    const cue = truncated !== formatted.displayText
      ? { ...formatted, displayText: truncated }
      : formatted
    // Single prepare — reuse for both layout and shrinkwrap
    const p = prepareWithSegments(cue.displayText, FONT_SPEECH)
    const r = layout(p, bubbleMaxTextW, LH_SPEECH)
    let maxW = 0
    walkLineRanges(p, bubbleMaxTextW, (line) => { if (line.width > maxW) maxW = line.width })
    return { ...cue, textW: Math.ceil(maxW), textH: r.height }
  }

  // Chip — single prepare for both layout and shrinkwrap
  const p = prepareWithSegments(formatted.displayText, FONT_CHIP)
  const r = layout(p, bubbleMaxTextW, LH_CHIP)
  let maxW = 0
  walkLineRanges(p, bubbleMaxTextW, (line) => { if (line.width > maxW) maxW = line.width })
  return { ...formatted, textW: Math.ceil(maxW), textH: r.height }
}

/** Full pipeline: StreamRecord → MeasuredCue | null. */
export function processRecord(
  record: StreamRecord,
  actionDefs: Record<string, any>,
): MeasuredCue | null {
  const raw = classify(record, actionDefs)
  if (!raw) return null
  const formatted = format(raw, actionDefs)
  return measure(formatted)
}
