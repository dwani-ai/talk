const API_BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

function buildUrl(path) {
  if (!path.startsWith('/')) return `${API_BASE}/${path}`
  return `${API_BASE}${path}`
}

export async function fetchJson(path, { method = 'GET', headers, body, signal } = {}) {
  const url = buildUrl(path)
  const res = await fetch(url, {
    method,
    headers: {
      Accept: 'application/json',
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(headers || {}),
    },
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'include',
    signal,
  })

  let data = null
  const contentType = res.headers.get('Content-Type') || ''
  if (contentType.includes('application/json')) {
    data = await res.json().catch(() => null)
  } else {
    const text = await res.text().catch(() => '')
    data = text ? { detail: text } : null
  }

  if (!res.ok) {
    const message =
      (data && (data.detail || data.message || data.error?.message)) ||
      `Request failed (${res.status})`
    const err = new Error(message)
    err.status = res.status
    err.data = data
    throw err
  }

  return data
}

export function withApiKey(headers, apiKey) {
  if (!apiKey) return headers || {}
  return { ...(headers || {}), 'X-API-Key': apiKey }
}

