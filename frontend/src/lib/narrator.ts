/* WorldSeed — Narrator style definitions (shared across stores + components) */

export const NARRATOR_STYLES = [
  'storyteller', 'poet', 'intel', 'noir', 'gossip',
  'conspiracy', 'bureaucrat', 'gameshow', 'trickster',
] as const

export type NarratorStyle = typeof NARRATOR_STYLES[number] | 'custom'

/** i18n key for a narrator style's description. */
export function narratorDescKey(style: NarratorStyle): string {
  return `narrator.${style}Desc`
}

/** Build the narrator payload for API calls (POST start / PATCH settings).
 *  Always sends both keys so the backend clears the unused one. */
export function buildNarratorPayload(style: NarratorStyle, prompt: string) {
  return {
    narrator_style: style === 'custom' ? '' : style,
    narrator_prompt: style === 'custom' ? prompt : '',
  }
}
