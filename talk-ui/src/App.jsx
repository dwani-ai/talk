import { useRef, useState, useCallback } from 'react'

const LANGUAGES = [
  { value: 'kannada', label: 'Kannada' },
  { value: 'hindi', label: 'Hindi' },
  { value: 'tamil', label: 'Tamil' },
]

const API_BASE = import.meta.env.VITE_API_URL || ''

export default function App() {
  const [language, setLanguage] = useState('kannada')
  const [status, setStatus] = useState('idle') // idle | recording | processing | playing | error
  const [error, setError] = useState(null)
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
        const url = `${API_BASE}/v1/speech_to_speech?language=${encodeURIComponent(language)}`
        const res = await fetch(url, {
          method: 'POST',
          body: formData,
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const audioBlob = await res.blob()
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
    [language]
  )

  const onDataAvailable = useCallback(
    (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data)
    },
    []
  )

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
      <header>
        <h1>Talk</h1>
        <p className="tagline">Push to talk · ASR → LLM → TTS</p>
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
      </footer>
    </div>
  )
}
