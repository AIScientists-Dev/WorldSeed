/* WorldSeed — Stream record formatting.
 *
 * Single source of truth for:
 * - HIDDEN_KINDS: which kinds to exclude from default view + kind counts
 * - KIND_DISPLAY: how to group kinds in filter chips
 * - recClass: CSS class per record
 * - hasFreeText: whether an action has a free_text param (drives rendering)
 */

/** Kinds hidden from All view (shown only when explicitly filtered). */
export const HIDDEN_KINDS = new Set(['perceive', 'wakeup'])

/** Kinds hidden in Digest view — no agent thinking, no engine internals. */
export const DIGEST_HIDDEN_KINDS = new Set(['perceive', 'wakeup', 'agent_text', 'action'])

/** Kinds hidden in Story view — hides engine plumbing, keeps narrative. */
export const STORY_HIDDEN_KINDS = new Set(['perceive', 'wakeup', 'consequence', 'action'])

/** Agent text responses that are no-op replies (filtered from all views). */
export const AGENT_NOOP_REPLIES = new Set(['NO_REPLY', '[[reply_to_current]] NO_REPLY'])

/** Map raw kind to display group for filter chips. */
export const KIND_DISPLAY: Record<string, string> = {
  dm_call: 'dm',
  gm_resolve: 'dm',
  consequence: 'event',
  gm_resolve_queued: 'user',
  whisper: 'user',
  gm_set: 'user',
  gm_set_queued: 'user',
  gm_remove: 'user',
  gm_remove_queued: 'user',
}

/** Check if an action has a free_text param (drives dialogue vs compact rendering). */
export function hasFreeText(actionDefs: Record<string, any>, actionType: string): boolean {
  const def = actionDefs[actionType]
  if (!def?.params) return false
  return def.params.some((p: any) => p.type === 'free_text')
}

/** Extract the free_text param value from action params. */
export function extractFreeText(actionDefs: Record<string, any>, actionType: string, params: Record<string, unknown>): string | null {
  const def = actionDefs[actionType]
  if (!def?.params) return null
  const ftParam = def.params.find((p: any) => p.type === 'free_text')
  if (!ftParam) return null
  const val = params[ftParam.name]
  return typeof val === 'string' ? val : null
}

/** Format params as compact string, skipping free_text params (shown separately). */
export function formatParams(params: any, actionDefs?: Record<string, any>, actionType?: string): string {
  if (!params || typeof params !== 'object') return ''
  // Skip free_text params (rendered as dialogue text, not inline)
  const skip = new Set<string>()
  if (actionDefs && actionType) {
    const def = actionDefs[actionType]
    if (def?.params) {
      for (const p of def.params) {
        if (p.type === 'free_text') skip.add(p.name)
      }
    }
  }
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (skip.has(k)) continue
    parts.push(`${k}: ${v}`)
  }
  return parts.length ? parts.join(', ') : ''
}

export function formatEffect(eff: any): string {
  if (!eff) return ''
  const op = eff.operator || eff.op || '?'
  const target = eff.target || eff.path || ''
  const val = eff.value != null ? eff.value : ''
  const by = eff.by != null ? eff.by : ''
  if (op === 'set') return `${target} = ${typeof val === 'object' ? JSON.stringify(val) : val}`
  if (op === 'increment') return `${target} +${by || val}`
  if (op === 'decrement') return `${target} -${by || val}`
  if (op === 'create_entity') return `create ${eff.id || ''} (${eff.entity_type || eff.type || ''})`
  if (op === 'remove_entity') return `remove ${eff.id || target}`
  if (op === 'emit_event') return `event: ${eff.detail || eff.event_type || eff.type || ''}`
  if (op === 'move') return `${eff.entity || target} -> ${eff.destination || val}`
  return JSON.stringify(eff)
}

export function recClass(rec: any): string {
  if (rec.kind === 'action') {
    return 'stream-record stream-action' + (rec.success === false ? ' is-fail' : '')
  }
  if (rec.kind === 'dm_call' || rec.kind === 'gm_resolve') return 'stream-record stream-dm'
  if (rec.kind === 'agent_text') return 'stream-record stream-agent-text'
  if (rec.kind === 'event' || rec.kind === 'consequence') {
    const isCons = rec.kind === 'consequence' || rec.scope === 'admin' || rec.type === 'consequence' ||
      (rec.detail && rec.detail.toLowerCase().includes('consequence'))
    return 'stream-record stream-event-rec' + (isCons ? ' is-consequence' : '')
  }
  if (rec.kind === 'highlight') return 'stream-record stream-highlight'
  if (rec.kind === 'whisper') return 'stream-record stream-whisper'
  if (rec.kind === 'register') return 'stream-record stream-register'
  if (rec.kind === 'wakeup') return 'stream-record stream-wake'
  if (rec.kind in KIND_DISPLAY) return 'stream-record stream-gm'
  return 'stream-record'
}
