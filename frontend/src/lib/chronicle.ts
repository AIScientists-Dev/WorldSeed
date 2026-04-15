/** Chronicle data parsing — single source of truth for ChronicleBar + ChronicleSheet. */

export interface Whisper {
  target: string
  label: string
}

export interface Aside {
  text: string
  whispers: Whisper[]
}

export interface Chapter {
  num: number
  tick: number
  title: string
  tldr: string
  paragraphs: string[]
  asides: Aside[]
}

function parseWhisperLine(line: string): Whisper | null {
  const colonIdx = line.indexOf(':')
  if (colonIdx <= 0) return null
  return { target: line.slice(0, colonIdx).trim(), label: line.slice(colonIdx + 1).trim() }
}

/** Parse asides + whisper_options as two separate fields, paired by position */
function parseAsidesAndWhispers(asidesRaw: string, whispersRaw: string): Aside[] {
  const trimmedAsides = asidesRaw.trim()
  const asideBlocks = trimmedAsides
    ? trimmedAsides.split(/\n\n+/)
        .map(b => b.split('\n').filter(l => !l.trim().startsWith('→') && !l.trim().startsWith('->')).join(' ').trim())
        .filter(Boolean)
    : []
  const trimmedWhispers = whispersRaw.trim()
  const whisperLines = trimmedWhispers ? trimmedWhispers.split(/\n+/).filter(Boolean) : []

  return asideBlocks.map((text, i) => {
    const whispers: Whisper[] = []
    const w = whisperLines[i]
    if (w) {
      const parsed = parseWhisperLine(w)
      if (parsed) whispers.push(parsed)
    }
    return { text, whispers }
  })
}

/** Extract all narrator chapters from stream records */
export function extractChapters(records: any[]): Chapter[] {
  const chapters: Chapter[] = []
  let num = 0
  for (const rec of records) {
    if (rec.kind === 'action' && rec.highlight && rec.agent_id === 'narrator') {
      num++
      const title = (rec.params?.title || '').trim()
      const tldr = (rec.params?.tldr || '').trim()
      const body = (rec.params?.body || rec.params?.summary || '').trim()
      const paragraphs = body.split(/\n\n+/).map((p: string) => p.trim()).filter(Boolean)
      // "ironies" fallback: old stream records use the pre-rename field name
      const asides = parseAsidesAndWhispers(rec.params?.asides || rec.params?.ironies || '', rec.params?.whisper_options || '')
      chapters.push({ num, tick: rec.tick, title: title || `§${num}`, tldr, paragraphs, asides })
    }
  }
  return chapters
}

/** Extract just the latest chapter at or before maxTick (for ChronicleBar) */
export function extractLatestChapter(records: any[], maxTick?: number): Chapter | null {
  const chapters = extractChapters(records)
  if (maxTick !== undefined) {
    const visible = chapters.filter(c => c.tick <= maxTick)
    return visible.length > 0 ? visible[visible.length - 1] : null
  }
  return chapters.length > 0 ? chapters[chapters.length - 1] : null
}
