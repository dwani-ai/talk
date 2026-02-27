import { useRef, useState, useCallback } from 'react'

const SESSION_KEY = 'talk_session_id'

function getOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
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
  const [mode, setMode] = useState('llm') // 'llm' or 'agent'
  const [agentName, setAgentName] = useState('travel_planner')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)
  const [conversations, setConversations] = useState([])
  const [sidebarOpen, setSidebarOpen] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= 768
  )
  const [sessionId, setSessionId] = useState(() => getOrCreateSessionId())
  const [typedMessage, setTypedMessage] = useState('')
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])
  const streamRef = useRef(null)

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
        setError(e.message || 'Request failed')
        setStatus('idle')
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
    }
  }, [typedMessage, status, mode, agentName, sessionId])

  const statusLabel =
    status === 'recording'
      ? 'Recording…'
      : status === 'processing'
        ? 'Processing…'
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
          <h1>Talk</h1>
          <p className="tagline">
            Push to talk · ASR → {mode === 'agent' ? 'Agent' : 'LLM'} → TTS
          </p>
        </header>

        <div className="controls">
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
                }
              }}
              disabled={status !== 'idle'}
            >
              <option value="llm">Chatbot (LLM)</option>
              <option value="agent_travel">Travel planner agent</option>
              <option value="agent_viva">Viva/voce examiner</option>
              <option value="agent_fix_my_city">Fix my city agent</option>
            </select>
          </label>

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

        {error && (
          <div className="error" role="alert">
            {error}
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
