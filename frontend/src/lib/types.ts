/* WorldSeed — Shared TypeScript interfaces for stores and lib modules.
 * All shapes match the server API responses.
 */

/** Core entity from /api/state */
export interface Entity {
  id: string
  type: string
  properties: Record<string, unknown>
  relationships?: { type: string; target: string; value?: unknown }[]
  [key: string]: unknown  // allow extra fields from enrichEntities
}

/** Enrich raw entity objects from API with a `properties` map. */
export function enrichEntities(raw: any[]): Entity[] {
  return (raw || []).map(e => {
    const props: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(e)) {
      if (k !== 'id' && k !== 'type') props[k] = v
    }
    return { ...e, properties: props } as Entity
  })
}

/** Event from /api/events */
export interface WorldEvent {
  tick: number
  type: string
  source?: string
  target?: string
  detail?: string
  scope?: string
  action?: string
  agent_id?: string
  [key: string]: unknown
}

/** Character from /characters */
export interface Character {
  id: string
  character: Record<string, unknown>
}

/** DM effect from stream */
export interface DmEffect {
  operator?: string
  target?: string
  path?: string
  value?: unknown
  by?: unknown
  [key: string]: unknown
}

/** SSE stream record */
export interface StreamRecord {
  kind: string
  tick?: number
  agent_id?: string
  action_type?: string
  action?: string
  source?: string
  target?: string
  type?: string
  scope?: string
  detail?: string
  narrative?: string
  effects?: DmEffect[]
  tokens_in?: number
  tokens_out?: number
  // Action records
  params?: Record<string, unknown>
  success?: boolean
  reason?: string
  text?: string
  // Perceive records
  visible_agent_ids?: string[]
  visible_entity_ids?: string[]
  events_delivered?: number
  [key: string]: unknown
}

/** Agent perception from /api/inbox */
export interface AgentPerception {
  self_state: Record<string, unknown> | null
  nearby_entities: Record<string, Record<string, unknown>>
  nearby_agents: Record<string, Record<string, unknown>>
  // Legacy field names (some API versions use these)
  visible_entities?: Record<string, Record<string, unknown>>
  visible_agents?: Record<string, Record<string, unknown>>
  events: unknown[]
  whispers: unknown[]
  action_options: Record<string, unknown>
}
