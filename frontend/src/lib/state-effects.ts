/* WorldSeed — Shared state_effects matching.
 *
 * Parses condition strings from UI config bind.state_effects and evaluates
 * them against entity properties. Supports =, <, > operators.
 *
 * Returns the matched preset name (e.g. "destroyed", "active").
 * EntityCard applies as CSS class `entity-state-${preset}`.
 *
 * Available presets: active, damaged, destroyed, locked, disabled, highlighted, warning
 */

const RE_LT = /^(.+)<(\d+)$/
const RE_GT = /^(.+)>(\d+)$/
const RE_EQ = /^(.+)=(.+)$/

/** Evaluate state_effects against an entity, return first matched preset or null. */
export function matchStateEffect(
  entity: Record<string, any>,
  effects: Record<string, string>,
): string | null {
  for (const [condition, preset] of Object.entries(effects)) {
    const ltMatch = condition.match(RE_LT)
    if (ltMatch) {
      const val = Number(entity[ltMatch[1]])
      if (!isNaN(val) && val < Number(ltMatch[2])) return preset
      continue
    }
    const gtMatch = condition.match(RE_GT)
    if (gtMatch) {
      const val = Number(entity[gtMatch[1]])
      if (!isNaN(val) && val > Number(gtMatch[2])) return preset
      continue
    }
    const eqMatch = condition.match(RE_EQ)
    if (eqMatch) {
      if (String(entity[eqMatch[1]]) === eqMatch[2]) return preset
    }
  }
  return null
}
