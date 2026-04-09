import { fetchJson, withApiKey } from './http'

export async function sendChatRequest({ text, mode, agentName, sessionId, apiKey }) {
  const headers = withApiKey(
    sessionId ? { 'X-Session-ID': sessionId } : undefined,
    apiKey
  )
  return await fetchJson('/v1/chat', {
    method: 'POST',
    headers,
    body: {
      text,
      mode,
      agent_name: mode === 'agent' ? agentName : undefined,
    },
  })
}

export async function sendSpeechRequest({ blob, mode, agentName, sessionId, apiKey }) {
  const headers = withApiKey(
    sessionId ? { 'X-Session-ID': sessionId } : undefined,
    apiKey
  )

  const params = new URLSearchParams()
  params.set('mode', mode)
  if (mode === 'agent' && agentName) params.set('agent_name', agentName)
  params.set('format', 'json')

  const form = new FormData()
  form.append('file', blob, 'audio.webm')

  const url = `/v1/speech_to_speech?${params.toString()}`
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: form,
    credentials: 'include',
  })
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const err = new Error((data && (data.detail || data.message)) || `Request failed (${res.status})`)
    err.status = res.status
    err.data = data
    throw err
  }
  return data
}

