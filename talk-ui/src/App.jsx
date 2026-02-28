import { useRef, useState, useCallback, useEffect } from 'react'
import { Link, NavLink } from 'react-router-dom'
import { sendChatRequest, sendSpeechRequest } from './lib/apiClient'
import { base64ToBlob } from './lib/audio'
import { createSessionId, getOrCreateSessionId, loadConversations, saveConversations, setSessionId as persistSessionId } from './lib/session'
import { useAudioRecorder } from './hooks/useAudioRecorder'
import { useAuth } from './contexts/AuthContext'


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

const API_KEY = import.meta.env.VITE_API_KEY || ''

export default function App() {
  const { currentUser, isAuthenticated, logout } = useAuth()
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
  const currentAudioRef = useRef(null)

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
      try {
        const data = await sendSpeechRequest({
          blob,
          language,
          mode: mode === 'agent' ? 'agent' : 'llm',
          agentName,
          sessionId,
          apiKey: API_KEY,
        })
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
        currentAudioRef.current = audio
        setStatus('playing')
        audio.onended = () => {
          URL.revokeObjectURL(audioUrl)
          currentAudioRef.current = null
          setStatus('idle')
        }
        audio.onerror = () => {
          URL.revokeObjectURL(audioUrl)
          currentAudioRef.current = null
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

  const { startRecording, stopRecording } = useAudioRecorder(sendAndPlay)

  useEffect(() => {
    return () => {
      stopRecording()
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }
    }
  }, [stopRecording])

  const startNewConversation = useCallback(() => {
    const newId = createSessionId()
    persistSessionId(newId)
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

  const handlePointerDown = () => {
    if (status !== 'idle' && status !== 'error') return
    setError(null)
    startRecording()
      .then(() => setStatus('recording'))
      .catch(() => {
        setError('Microphone access denied or unavailable')
        setStatus('idle')
      })
  }

  const handlePointerUp = () => {
    if (status === 'recording') stopRecording()
  }

  const handlePointerLeave = () => {
    if (status === 'recording') stopRecording()
  }

  const handleMicKeyDown = (e) => {
    if (e.key !== ' ' && e.key !== 'Enter') return
    e.preventDefault()
    if (status !== 'idle' && status !== 'error') return
    handlePointerDown()
  }

  const handleMicKeyUp = (e) => {
    if (e.key !== ' ' && e.key !== 'Enter') return
    e.preventDefault()
    if (status === 'recording') stopRecording()
  }

  const sendTypedMessage = useCallback(async () => {
    const text = typedMessage.trim()
    if (!text || status !== 'idle') return

    setStatus('processing')
    setError(null)

    try {
      const data = await sendChatRequest({
        text,
        mode: mode === 'agent' ? 'agent' : 'llm',
        agentName,
        sessionId,
        apiKey: API_KEY,
      })
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
      lastFailedRequestRef.current = null
      setStatus('processing')
      sendChatRequest({
        text: last.text,
        mode: mode === 'agent' ? 'agent' : 'llm',
        agentName,
        sessionId,
        apiKey: API_KEY,
      })
        .then((data) => {
          setConversations((prev) => [...prev, { id: Date.now(), user: last.text, assistant: data.reply || '(no response)', timestamp: new Date().toLocaleTimeString() }])
          setTypedMessage('')
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
          <label htmlFor="typed-message" className="sr-only">Type message</label>
          <textarea
            id="typed-message"
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
            <div className="header-brand">
              <h1>dwani.ai</h1>
              <p className="tagline">
                Conversational AI Agents for Indian languages <br />
              </p>
              <p className="tagline">Push to talk · ASR → {mode === 'agent' ? 'Agent' : 'LLM'} → TTS</p>
            </div>
            <div className="header-actions">
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
              <div className="auth-nav">
                {isAuthenticated ? (
                  <>
                    <span className="auth-email" title={currentUser?.email}>{currentUser?.email}</span>
                    <button type="button" className="auth-btn" onClick={logout}>Log out</button>
                  </>
                ) : (
                  <>
                    <Link to="/login" className="auth-link">Log in</Link>
                    <Link to="/signup" className="auth-link auth-link-primary">Sign up</Link>
                  </>
                )}
              </div>
            </div>
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
            onKeyDown={handleMicKeyDown}
            onKeyUp={handleMicKeyUp}
            disabled={status === 'processing'}
            aria-label={statusLabel}
          >
            <span className="icon">{status === 'recording' ? '⏹' : '🎤'}</span>
            <span className="label">{statusLabel}</span>
          </button>
        </div>

        {!isOnline && (
          <div className="offline" role="status" aria-live="polite">
            You are offline. Check your connection.
          </div>
        )}
        {error && (
          <div className="error" role="alert" aria-live="assertive">
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
