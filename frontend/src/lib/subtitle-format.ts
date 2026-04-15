/* WorldSeed — Subtitle formatter: RawCue → FormattedCue.
 *
 * Transforms raw classifier output into display-ready text.
 * Scene-agnostic: reads actionType + params, never hardcodes action names.
 */

import type { RawCue, FormattedCue } from './subtitle-types'

let nextId = 0

/**
 * Format a raw cue into display-ready text.
 *
 * - speech: quoted free text
 * - narrative: DM narrative text
 * - action (chip): "actionType → param1, param2" or just "actionType"
 */
export function format(
  raw: RawCue,
  actionDefs: Record<string, any>,
): FormattedCue {
  const id = `cue-${++nextId}`

  if (raw.kind === 'speech') {
    return { ...raw, id, displayText: raw.freeText || '' }
  }

  if (raw.kind === 'narrative' || raw.kind === 'description') {
    return { ...raw, id, displayText: raw.narrative || '' }
  }

  // Action chip: use narrative (event detail) if available, else build from params
  if (raw.narrative) {
    return { ...raw, id, displayText: raw.narrative }
  }

  const def = actionDefs[raw.actionType]
  const paramParts: string[] = []
  if (def?.params) {
    for (const p of def.params) {
      if (p.type === 'free_text') continue
      const val = raw.params[p.name]
      if (val != null && val !== '') paramParts.push(String(val))
    }
  }

  const displayText = paramParts.length > 0
    ? `${raw.actionType} → ${paramParts.join(', ')}`
    : raw.actionType

  return { ...raw, id, displayText }
}
