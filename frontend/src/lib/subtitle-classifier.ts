/* WorldSeed — Subtitle classifier: StreamRecord → RawCue.
 *
 * Event-driven: subtitles come from event records only.
 *   - Action echo events (event.type matches an action name with free_text) → speech bubble
 *   - Action echo events (event.type matches an action name, no free_text) → action chip
 *   - god_announce / UI config bubble="speech" → speech bubble
 *   - Other events → narrative (bottom bar)
 *
 * Drop rules:
 *   - admin scope events
 *   - target_only scope events
 *   - events with no detail
 *   - non-event records (action, wakeup, register, consequence)
 *
 * DM calls → description bubble (kept as separate path).
 */

import type { StreamRecord } from '@/lib/types'
import type { RawCue } from './subtitle-types'
import { hasFreeText } from '@/lib/stream-format'
import { uiConfig } from '@/lib/ui-config'

function cue(
  kind: RawCue['kind'], agentId: string, actionType: string,
  freeText: string | null, narrative: string | null, tick: number,
  params: Record<string, unknown> = {},
): RawCue {
  return { kind, agentId, actionType, params, freeText, narrative, tick }
}

export function classify(
  record: StreamRecord,
  actionDefs: Record<string, any>,
): RawCue | null {
  // DM call → description bubble
  if ((record.kind === 'dm_call' || record.kind === 'gm_resolve') && record.narrative
      && !record.narrative.startsWith('(DM call failed')) {
    return cue('description', record.agent_id || '', record.action || '',
      null, record.narrative, record.tick ?? 0, record.params || {})
  }

  // Narrator highlights have their own dedicated render path (ChronicleBar).
  // Do NOT route them through the subtitle pipeline.

  // Only events produce subtitles
  if (record.kind !== 'event' || !record.detail) return null

  const scope = record.scope || ''
  const eventType = record.type || ''
  const source = record.source || ''
  const tick = record.tick ?? 0

  if (scope === 'admin' || scope === 'target_only') return null

  // Action echo with free_text → speech bubble
  if (actionDefs[eventType] && hasFreeText(actionDefs, eventType)) {
    return cue('speech', source, eventType, record.detail, null, tick)
  }

  // Action echo without free_text → chip
  if (actionDefs[eventType]) {
    return cue('action', source, eventType, null, record.detail, tick)
  }

  // UI config bubble="speech" → speech bubble (god_announce)
  if (uiConfig.getEventStyle(eventType) === 'speech') {
    return cue('speech', source, eventType, record.detail, null, tick)
  }

  // Everything else → narrative bar
  return cue('narrative', source, eventType, null, record.detail, tick)
}
