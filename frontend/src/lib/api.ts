/* WorldSeed — API client with error handling */

let _setError: ((msg: string) => void) | null = null

/** Called once from main.ts after stores are ready */
export function initApiErrorHandler(setter: (msg: string) => void) {
  _setError = setter
}

function setError(msg: string) {
  if (_setError) _setError(msg)
}

export async function apiFetch(url: string): Promise<any> {
  try {
    const r = await fetch(url)
    if (!r.ok) { setError(`${url}: ${r.status}`); return null }
    setError('')
    return await r.json()
  } catch (e: any) {
    setError(`${url}: ${e.message}`)
    return null
  }
}

async function apiMutate(method: string, url: string, body?: any): Promise<{ ok: boolean; data: any }> {
  try {
    const r = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!r.ok) setError(`${method} ${url}: ${r.status}`)
    else setError('')
    return { ok: r.ok, data: await r.json().catch(() => ({})) }
  } catch (e: any) {
    setError(`${method} ${url}: ${e.message}`)
    return { ok: false, data: {} }
  }
}

export function apiPost(url: string, body?: any) { return apiMutate('POST', url, body) }
export function apiPatch(url: string, body?: any) { return apiMutate('PATCH', url, body) }
