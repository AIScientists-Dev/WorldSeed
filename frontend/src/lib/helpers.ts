/* WorldSeed — Pure helper functions */

/** Replace underscores with spaces for display */
export function humanize(s: string): string { return s ? s.replace(/_/g, ' ') : '' }

export function esc(s: any): string {
  if (s == null) return ''
  const d = document.createElement('div')
  d.textContent = String(s)
  return d.innerHTML
}

export function formatVal(v: any): string {
  if (v == null) return '\u2014'
  if (Array.isArray(v)) return v.length ? v.map(formatVal).join(', ') : '\u2014'
  if (typeof v === 'object') {
    const entries = Object.entries(v)
    if (!entries.length) return '\u2014'
    return entries.map(([k, val]) => `${k}: ${formatVal(val)}`).join(', ')
  }
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  return String(v)
}

export function formatTime(ts: any): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleString() }
  catch { return ts }
}

export function isNoise(text: string): boolean {
  if (!text) return false
  const t = text.trim()
  return t.startsWith('Task: Hook |') ||
    t.startsWith('SECURITY NOTICE') ||
    t.includes('EXTERNAL_UNTRUSTED_CONTENT') ||
    t.includes('END_EXTERNAL_UNTRUSTED_CONTENT') ||
    t.includes('HEARTBEAT') ||
    t.startsWith('Read HEARTBEAT') ||
    t === 'HEARTBEAT_OK' ||
    t.startsWith('System: [') ||
    t.includes('prompt injection')
}

export function summarizePerception(jsonStr: string): string {
  try {
    const d = JSON.parse(jsonStr)
    const parts: string[] = []
    // Find location: any self_state string value that matches a nearby entity ID
    const ss = d.self_state || {}
    const nearbyIds = new Set(Object.keys(d.nearby_entities || d.visible_entities || {}))
    let loc = ''
    for (const v of Object.values(ss)) {
      if (typeof v === 'string' && nearbyIds.has(v)) { loc = v; break }
    }
    if (loc) parts.push('at ' + loc)
    const vis = Object.keys(d.nearby_agents || d.visible_agents || {})
    if (vis.length) parts.push('sees ' + vis.join(', '))
    const ents = Object.keys(d.nearby_entities || d.visible_entities || {})
    if (ents.length) parts.push('near ' + ents.join(', '))
    const evts = (d.events || []).length
    if (evts) parts.push(evts + ' event(s)')
    const whisperCount = (d.whispers || []).length
    if (whisperCount) parts.push(whisperCount + ' whisper(s)')
    return parts.join(' \u00b7 ') || 'empty perception'
  } catch {
    return jsonStr.slice(0, 80) + '...'
  }
}

export function summarizeActResult(jsonStr: string): string {
  try {
    const d = JSON.parse(jsonStr)
    if (d.queued) return 'queued at tick ' + d.tick
    if (d.detail) return d.detail
    return 'ok'
  } catch {
    return jsonStr.slice(0, 80)
  }
}

function _clampable(cls: string, html: string): string {
  return `<div class="clampable ${cls}" onclick="this.classList.toggle('is-expanded')">${html}</div>`
}

export function buildRawLogHtml(messages: any[]): string {
  const toolResults: Record<string, string> = {}
  messages.forEach(msg => {
    const role = msg.role || ''
    const ct = msg.content
    if (role === 'tool' || role === 'toolResult') {
      const id = msg.tool_use_id || msg.toolCallId || ''
      const text = typeof ct === 'string' ? ct
        : Array.isArray(ct) && ct[0]?.text ? ct[0].text : ''
      if (id && text) toolResults[id] = text
    }
  })

  let h = '<div class="chat-feed">'

  messages.forEach(msg => {
    const role = msg.role || 'unknown'
    const ct = msg.content

    if (role === 'user') {
      const texts = Array.isArray(ct)
        ? ct.filter((b: any) => b.type === 'text' && b.text).map((b: any) => b.text)
        : typeof ct === 'string' ? [ct] : []
      if (texts.length && texts.every(isNoise)) return
    }

    if (role === 'tool' || role === 'toolResult') return

    if (Array.isArray(ct)) {
      ct.forEach((b: any) => {
        if (b.type === 'thinking' && b.thinking) {
          h += `<div class="chat-think">${esc(b.thinking)}</div>`
        } else if (b.type === 'text' && b.text && !isNoise(b.text)) {
          const cls = role === 'user' ? 'is-user' : 'is-asst'
          h += role === 'user'
            ? _clampable('chat-bubble ' + cls, esc(b.text))
            : `<div class="chat-bubble ${cls}">${esc(b.text)}</div>`
        } else if (b.type === 'toolCall' || b.type === 'tool_use') {
          const name = b.name || ''
          const callId = b.id || ''
          const args = b.input || b.arguments || {}
          const isAct = name.includes('act')
          const isPerceive = name.includes('perceive')
          const raw = toolResults[callId] || ''

          const label = (isAct && args.action) ? args.action : name
          const toolCls = isAct ? ' is-act' : ''
          const params = Object.entries(args)
            .filter(([k]) => k !== 'agent_id' && k !== 'action')
          const inlineParams: [string, string][] = []
          const longParams: [string, string][] = []
          params.forEach(([k, v]) => {
            const val = typeof v === 'string' ? v : JSON.stringify(v)
            if (typeof v === 'string' && v.length > 60) {
              longParams.push([k, val])
            } else {
              inlineParams.push([k, val])
            }
          })
          let summary = ''
          if (raw) {
            summary = isPerceive ? summarizePerception(raw)
              : isAct ? summarizeActResult(raw)
              : (raw.length > 80 ? raw.slice(0, 80) + '...' : raw)
          }

          h += `<div class="chat-tool-group" onclick="this.classList.toggle('open')">`
          h += `<div class="chat-tool${toolCls}">`
          h += `<span class="tool-action-type">${esc(label)}</span>`
          inlineParams.forEach(([k, v]) => {
            h += `<span class="tool-param"><span class="tool-param-k">${esc(k)}:</span> ${esc(v)}</span>`
          })
          if (summary) h += `<span class="tool-result-badge">${esc(summary)}</span>`
          h += '</div>'
          longParams.forEach(([k, v]) => {
            h += `<div class="tool-long-param">`
            h += `<span class="tool-param-k">${esc(k)}:</span> ${esc(v)}`
            h += `</div>`
          })
          if (raw) h += `<div class="chat-result">${esc(raw)}</div>`
          h += '</div>'
        }
      })
    } else if (typeof ct === 'string' && !isNoise(ct)) {
      const cls = role === 'user' ? 'is-user' : 'is-asst'
      h += role === 'user'
        ? _clampable('chat-bubble ' + cls, esc(ct))
        : `<div class="chat-bubble ${cls}">${esc(ct)}</div>`
    }
  })

  h += '</div>'
  return h
}

