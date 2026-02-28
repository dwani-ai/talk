import { useRef, useState, useCallback, useEffect } from 'react'
import { Link, NavLink } from 'react-router-dom'

const SESSION_KEY = 'talk_session_id'
const CONVERSATIONS_KEY = 'talk_conversations'
const MAX_CONVERSATIONS_STORED = 50

function getOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

function loadConversations() {
  try {
    const raw = localStorage.getItem(CONVERSATIONS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.slice(-MAX_CONVERSATIONS_STORED) : []
  } catch {
    return []
  }
}

function saveConversations(list) {
  try {
    const toSave = list.slice(-MAX_CONVERSATIONS_STORED)
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(toSave))
  } catch (_) {}
}

const LANGUAGES = [
  { value: 'kannada', label: 'Kannada' },
  { value: 'hindi', label: 'Hindi' },
  { value: 'tamil', label: 'Tamil' },
  { value: 'malayalam', label: 'Malayalam' },
  { value: 'telugu', label: 'Telugu' },
  { value: 'marathi', label: 'Marathi' },
  { value: 'english', label: 'English' },
  { value: 'german', label: 'German' },
]

const API_BASE = import.meta.env.VITE_API_URL || ''

function base64ToBlob(base64, mime) {
  const byteChars = atob(base64)
  const byteNumbers = new Array(byteChars.length)
  for (let i = 0; i < byteChars.length; i++) {
    byteNumbers[i] = byteChars.charCodeAt(i)
  }
  return new Blob([new Uint8Array(byteNumbers)], { type: mime })
}

export default function App() {
  const [language, setLanguage] = useState('kannada')
  const [mode, setMode] = useState('agent') // 'llm' or 'agent'
  const [agentName, setAgentName] = useState('orchestrator')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [conversations, setConversations] = useState(loadConversations)
  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 768
  )
  const [sessionId, setSessionId] = useState(() => getOrCreateSessionId())
  const [typedMessage, setTypedMessage] = useState('')
  const [isOnline, setIsOnline] = useState(() => (typeof navigator !== 'undefined' ? navigator.onLine : true))
  const [canRetry, setCanRetry] = useState(false)
  const [progressStep, setProgressStep] = useState(null)
  const lastFailedRequestRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

  useEffect(() => {
    saveConversations(conversations)
  }, [conversations])

  useEffect(() => {
    if (status !== 'processing' || !progressStep) return
    const steps = ['transcribing', 'thinking', 'generating_speech']
    const idx = steps.indexOf(progressStep)
    const next = idx < 0 ? 'thinking' : steps[Math.min(idx + 1, steps.length - 1)]
    const t = setTimeout(() => setProgressStep(next), 2000)
    return () => clearTimeout(t)
  }, [status, progressStep])

  useEffect(() => {
    if (typeof window === 'undefined') return
    const onOnline = () => setIsOnline(true)
    const onOffline = () => setIsOnline(false)
    window.addEventListener('online', onOnline)
    window.addEventListener('offline', onOffline)
    return () => {
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
    }
  }, [])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }
  }, [])

  const sendAndPlay = useCallback(
    async (blob) => {
      if (!blob || blob.size === 0) {
        setStatus('idle')
        setError('No audio recorded')
        return
      }
      setStatus('processing')
      setError(null)
      setProgressStep('transcribing')
      const formData = new FormData()
      const ext = blob.type.includes('webm') ? 'webm' : 'wav'
      formData.append('file', blob, `recording.${ext}`)
      try {
        const isAgent = mode === 'agent'
        const params = new URLSearchParams({
          language,
          format: 'json',
          mode: isAgent ? 'agent' : 'llm',
        })
        if (isAgent) {
          params.set('agent_name', agentName)
        }
        const url = `${API_BASE}/v1/speech_to_speech?${params.toString()}`
        const res = await fetch(url, {
          method: 'POST',
          body: formData,
          headers: { 'X-Session-ID': sessionId },
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const data = await res.json()
        const { transcription, llm_response, audio_base64 } = data

        setConversations((prev) => [
          ...prev,
          {
            id: Date.now(),
            user: transcription || '(no transcription)',
            assistant: llm_response || '(no response)',
            timestamp: new Date().toLocaleTimeString(),
          },
        ])

        setProgressStep(null)
        const audioBlob = base64ToBlob(audio_base64, 'audio/mp3')
        const audioUrl = URL.createObjectURL(audioBlob)
        const audio = new Audio(audioUrl)
        setStatus('playing')
        audio.onended = () => {
          URL.revokeObjectURL(audioUrl)
          setStatus('idle')
        }
        audio.onerror = () => {
          URL.revokeObjectURL(audioUrl)
          setStatus('idle')
          setError('Failed to play response')
        }
        await audio.play()
      } catch (e) {
        setProgressStep(null)
        setError(e.message || 'Request failed')
        setStatus('idle')
        lastFailedRequestRef.current = { type: 'speech', blob }
        setCanRetry(true)
      }
    },
    [language, mode, agentName, sessionId]
  )

  const startNewConversation = useCallback(() => {
    const newId = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(SESSION_KEY, newId)
    setSessionId(newId)
    setConversations([])
    setError(null)
    saveConversations([])
  }, [])

  const clearHistory = useCallback(() => {
    setConversations([])
    saveConversations([])
    setError(null)
  }, [])

  const onDataAvailable = useCallback((e) => {
    if (e.data.size > 0) chunksRef.current.push(e.data)
  }, [])

  const onStop = useCallback(() => {
    const blob = new Blob(chunksRef.current, { type: 'audio/wav' })
    chunksRef.current = []
    sendAndPlay(blob)
  }, [sendAndPlay])

  const startRecording = useCallback(async () => {
    setError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      const recorder = new MediaRecorder(stream)
      mediaRecorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = onDataAvailable
      recorder.onstop = onStop
      recorder.start(200)
      setStatus('recording')
    } catch (e) {
      setError('Microphone access denied or unavailable')
      setStatus('idle')
    }
  }, [onDataAvailable, onStop])

  const handlePointerDown = () => {
    if (status !== 'idle' && status !== 'error') return
    startRecording()
  }

  const handlePointerUp = () => {
    if (status === 'recording') stopRecording()
  }

  const handlePointerLeave = () => {
    if (status === 'recording') stopRecording()
  }

  const sendTypedMessage = useCallback(async () => {
    const text = typedMessage.trim()
    if (!text || status !== 'idle') return

    setStatus('processing')
    setError(null)

    try {
      const isAgent = mode === 'agent'
      const payload = {
        text,
        mode: isAgent ? 'agent' : 'llm',
      }
      if (isAgent) {
        payload.agent_name = agentName
      }

      const res = await fetch(`${API_BASE}/v1/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Session-ID': sessionId,
        },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Server error ${res.status}`)
      }

      const data = await res.json()
      const assistant = data.reply || '(no response)'

      setConversations((prev) => [
        ...prev,
        {
          id: Date.now(),
          user: text,
          assistant,
          timestamp: new Date().toLocaleTimeString(),
        },
      ])
      setTypedMessage('')
      setStatus('idle')
    } catch (e) {
      setError(e.message || 'Request failed')
      setStatus('idle')
      lastFailedRequestRef.current = { type: 'chat', text: typedMessage.trim() }
      setCanRetry(true)
    }
  }, [typedMessage, status, mode, agentName, sessionId])

  const retryLastRequest = useCallback(() => {
    const last = lastFailedRequestRef.current
    setError(null)
    setCanRetry(false)
    if (last?.type === 'speech' && last.blob) {
      sendAndPlay(last.blob)
    } else if (last?.type === 'chat' && last.text) {
      setTypedMessage(last.text)
      setStatus('idle')
      lastFailedRequestRef.current = null
      setStatus('processing')
      const payload = { text: last.text, mode: mode === 'agent' ? 'agent' : 'llm' }
      if (mode === 'agent') payload.agent_name = agentName
      fetch(`${API_BASE}/v1/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Session-ID': sessionId },
        body: JSON.stringify(payload),
      })
        .then((res) => {
          if (!res.ok) return res.json().then((err) => { throw new Error(err.detail || `Server error ${res.status}`) })
          return res.json()
        })
        .then((data) => {
          setConversations((prev) => [...prev, { id: Date.now(), user: last.text, assistant: data.reply || '(no response)', timestamp: new Date().toLocaleTimeString() }])
          setStatus('idle')
        })
        .catch((e) => {
          setError(e.message || 'Request failed')
          lastFailedRequestRef.current = { type: 'chat', text: last.text }
          setCanRetry(true)
          setStatus('idle')
        })
      return
    }
    lastFailedRequestRef.current = null
  }, [sendAndPlay, mode, agentName, sessionId])

  const progressStepLabels = {
    transcribing: 'Transcribing…',
    thinking: 'Thinking…',
    generating_speech: 'Generating speech…',
  }
  const statusLabel =
    status === 'recording'
      ? 'Recording…'
      : status === 'processing'
        ? (progressStep && progressStepLabels[progressStep]) || 'Processing…'
        : status === 'playing'
          ? 'Playing reply…'
          : 'Hold to talk'

  return (
    <div className="app">
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <h2>Conversations</h2>
          <div className="sidebar-actions">
            <button
              className="btn-new"
              onClick={startNewConversation}
              aria-label="Start new conversation"
            >
              New
            </button>
            {conversations.length > 0 && (
              <button
                className="btn-clear"
                onClick={clearHistory}
                aria-label="Clear history"
              >
                Clear history
              </button>
            )}
            <button
              className="sidebar-close"
              onClick={() => setSidebarOpen(false)}
              aria-label="Close sidebar"
            >
              ×
            </button>
          </div>
        </div>
        <div className="conversation-list">
          {conversations.length === 0 ? (
            <p className="empty">No conversations yet. Hold the mic and speak.</p>
          ) : (
            conversations.map((c) => (
              <div key={c.id} className="conversation-item">
                <div className="conv-meta">{c.timestamp}</div>
                <div className="conv-user">
                  <span className="conv-label">You</span>
                  <p>{c.user}</p>
                </div>
                <div className="conv-assistant">
                  <span className="conv-label">Reply</span>
                  <p>{c.assistant}</p>
                </div>
              </div>
            ))
          )}
        </div>
        <div className="conversation-input">
          <textarea
            rows={2}
            placeholder="Type your message…"
            value={typedMessage}
            onChange={(e) => setTypedMessage(e.target.value)}
            disabled={status !== 'idle'}
          />
          <button
            className="btn-send"
            onClick={sendTypedMessage}
            disabled={status !== 'idle' || !typedMessage.trim()}
          >
            Send
          </button>
        </div>
      </aside>

      <main className="main">
        <button
          className="sidebar-toggle"
          onClick={() => setSidebarOpen(true)}
          aria-label="Open conversations"
          title="View conversations"
        >
          💬 {conversations.length > 0 && <span className="badge">{conversations.length}</span>}
        </button>

        <header>
          <div className="header-main">
            <div>
              <h1>dwani.ai</h1>
              <p className="tagline">
                Conversational AI Agents for Indian languages <br />
              </p>
              <p className="tagline">Push to talk · ASR → {mode === 'agent' ? 'Agent' : 'LLM'} → TTS</p>
            </div>
            <nav className="nav-tabs">
              <NavLink to="/" className="nav-tab" end>
                Talk
              </NavLink>
              <NavLink to="/warehouse" className="nav-tab">
                Warehouse
              </NavLink>
              <NavLink to="/chess" className="nav-tab">
                Chess
              </NavLink>
            </nav>
          </div>
        </header>

        <div className="controls">
          <div className="controls-row">
          <label>
            Language
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              disabled={status !== 'idle'}
            >
              {LANGUAGES.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>

          <label>
            Mode
            <select
              value={
                mode === 'llm'
                  ? 'llm'
                  : agentName === 'viva_examiner'
                    ? 'agent_viva'
                    : agentName === 'fix_my_city'
                      ? 'agent_fix_my_city'
                      : agentName === 'warehouse_orchestrator'
                        ? 'agent_warehouse'
                        : agentName === 'chess_orchestrator'
                          ? 'agent_chess'
                        : agentName === 'orchestrator'
                          ? 'agent_orchestrator'
                          : 'agent_travel'
              }
              onChange={(e) => {
                const value = e.target.value
                if (value === 'llm') {
                  setMode('llm')
                  setAgentName('travel_planner')
                } else if (value === 'agent_travel') {
                  setMode('agent')
                  setAgentName('travel_planner')
                } else if (value === 'agent_viva') {
                  setMode('agent')
                  setAgentName('viva_examiner')
                } else if (value === 'agent_fix_my_city') {
                  setMode('agent')
                  setAgentName('fix_my_city')
                } else if (value === 'agent_orchestrator') {
                  setMode('agent')
                  setAgentName('orchestrator')
                } else if (value === 'agent_warehouse') {
                  setMode('agent')
                  setAgentName('warehouse_orchestrator')
                } else if (value === 'agent_chess') {
                  setMode('agent')
                  setAgentName('chess_orchestrator')
                }
              }}
              disabled={status !== 'idle'}
            >
              <option value="llm">Chatbot (LLM)</option>
              <option value="agent_travel">Travel planner agent</option>
              <option value="agent_viva">Viva/voce examiner</option>
              <option value="agent_fix_my_city">Fix my city agent</option>
              <option value="agent_orchestrator">All-in-one assistant</option>
              <option value="agent_warehouse">Warehouse robots (UAV / UGV / Arm)</option>
              <option value="agent_chess">Chess orchestrator</option>
            </select>
          </label>
          </div>

          <button
            className={`mic ${status}`}
            onPointerDown={handlePointerDown}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerLeave}
            disabled={status === 'processing'}
            aria-label={statusLabel}
          >
            <span className="icon">{status === 'recording' ? '⏹' : '🎤'}</span>
            <span className="label">{statusLabel}</span>
          </button>
        </div>

        {!isOnline && (
          <div className="offline" role="status">
            You are offline. Check your connection.
          </div>
        )}
        {error && (
          <div className="error" role="alert">
            <span>{error}</span>
            {canRetry && (
              <button type="button" className="btn-retry" onClick={retryLastRequest}>
                Retry
              </button>
            )}
          </div>
        )}

        <footer>
          <small>Hold the button, speak, then release to get a reply.</small>
          <button className="btn-new-inline" onClick={startNewConversation}>
            New conversation
          </button>
        </footer>
      </main>
    </div>
  )
}
