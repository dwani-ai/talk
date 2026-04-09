const SESSION_KEY = 'dwani_session_id'
const CONV_KEY = 'dwani_conversations'

export function createSessionId() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

export function setSessionId(id) {
  if (!id) return
  try {
    localStorage.setItem(SESSION_KEY, id)
  } catch (_) {
    // ignore
  }
}

export function getOrCreateSessionId() {
  try {
    const existing = localStorage.getItem(SESSION_KEY)
    if (existing) return existing
  } catch (_) {
    // ignore
  }
  const id = createSessionId()
  setSessionId(id)
  return id
}

export function loadConversations() {
  try {
    const raw = localStorage.getItem(CONV_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch (_) {
    return []
  }
}

export function saveConversations(conversations) {
  try {
    localStorage.setItem(CONV_KEY, JSON.stringify(conversations || []))
  } catch (_) {
    // ignore
  }
}

