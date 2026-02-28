import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

const API_BASE = import.meta.env.VITE_API_URL || ''
const SESSION_KEY = 'talk_session_id'
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1']

const PIECE_TO_GLYPH = {
  wK: '♔',
  wQ: '♕',
  wR: '♖',
  wB: '♗',
  wN: '♘',
  wP: '♙',
  bK: '♚',
  bQ: '♛',
  bR: '♜',
  bB: '♝',
  bN: '♞',
  bP: '♟',
}

function getOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

export default function ChessView() {
  const [sessionId] = useState(() => getOrCreateSessionId())
  const [state, setState] = useState({
    board: {},
    turn: 'white',
    mode: 'human_vs_ai',
    status: 'in_progress',
    move_history: [],
    human_side: 'white',
  })
  const [mode, setMode] = useState('human_vs_ai')
  const [humanSide, setHumanSide] = useState('white')
  const [command, setCommand] = useState('')
  const [chatStatus, setChatStatus] = useState('idle')
  const [chatLog, setChatLog] = useState([])
  const [error, setError] = useState(null)

  const applyState = useCallback((data) => {
    if (!data || typeof data !== 'object') return
    setState({
      board: data.board || {},
      turn: data.turn || 'white',
      mode: data.mode || 'human_vs_ai',
      status: data.status || 'in_progress',
      move_history: Array.isArray(data.move_history) ? data.move_history : [],
      human_side: data.human_side || 'white',
    })
  }, [])

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/chess/state`)
      if (!res.ok) {
        throw new Error(`Server error ${res.status}`)
      }
      const data = await res.json()
      applyState(data)
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load chess state')
    }
  }, [applyState])

  useEffect(() => {
    fetchState()
    const id = setInterval(fetchState, 1200)
    return () => clearInterval(id)
  }, [fetchState])

  const sendCommand = useCallback(
    async (text) => {
      const msg = text.trim()
      if (!msg || chatStatus === 'sending') return
      setChatStatus('sending')
      setError(null)
      try {
        const res = await fetch(`${API_BASE}/v1/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Session-ID': sessionId,
          },
          body: JSON.stringify({
            text: msg,
            mode: 'agent',
            agent_name: 'chess_orchestrator',
          }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const data = await res.json()
        const assistant = data.reply || '(no response)'
        setChatLog((prev) => [...prev, { id: Date.now(), user: msg, assistant }])
        if (data.chess_state && typeof data.chess_state === 'object') {
          applyState(data.chess_state)
        } else {
          await fetchState()
        }
        setChatStatus('idle')
        return data
      } catch (e) {
        setError(e.message || 'Command failed')
        setChatStatus('idle')
        return null
      }
    },
    [applyState, chatStatus, fetchState, sessionId]
  )

  const onSubmit = useCallback(
    async (e) => {
      e.preventDefault()
      const text = command.trim()
      if (!text) return
      await sendCommand(text)
      setCommand('')
    },
    [command, sendCommand]
  )

  const startNewGame = useCallback(async () => {
    await sendCommand(`new game ${mode === 'human_vs_human' ? 'human vs human' : 'human vs ai'} as ${humanSide}`)
  }, [mode, humanSide, sendCommand])

  const squares = useMemo(() => {
    const out = []
    for (const rank of RANKS) {
      for (const file of FILES) {
        const sq = `${file}${rank}`
        out.push({
          square: sq,
          piece: state.board?.[sq] || null,
          dark: (FILES.indexOf(file) + Number(rank)) % 2 === 0,
        })
      }
    }
    return out
  }, [state.board])

  return (
    <div className="app">
      <main className="main warehouse-main">
        <header>
          <div className="header-main">
            <div>
              <h1>Chess</h1>
              <p className="tagline">Play chess with agent-driven commands and live board sync.</p>
            </div>
            <nav className="nav-tabs">
              <Link to="/" className="nav-tab">
                Talk
              </Link>
              <Link to="/warehouse" className="nav-tab">
                Warehouse
              </Link>
              <Link to="/chess" className="nav-tab">
                Chess
              </Link>
            </nav>
          </div>
        </header>

        <div className="warehouse-layout">
          <div className="warehouse-canvas chess-board-wrap">
            <div className="chess-board">
              {squares.map((s) => (
                <div key={s.square} className={`chess-square ${s.dark ? 'dark' : 'light'}`}>
                  <span className={`chess-piece ${s.piece?.startsWith('w') ? 'white-piece' : s.piece?.startsWith('b') ? 'black-piece' : ''}`}>
                    {s.piece ? PIECE_TO_GLYPH[s.piece] || s.piece : ''}
                  </span>
                  <span className="chess-label">{s.square}</span>
                </div>
              ))}
            </div>
          </div>

          <aside className="warehouse-sidebar">
            <h2>Game controls</h2>
            <label>
              Mode
              <select value={mode} onChange={(e) => setMode(e.target.value)} disabled={chatStatus === 'sending'}>
                <option value="human_vs_ai">Human vs AI</option>
                <option value="human_vs_human">Human vs Human</option>
              </select>
            </label>
            <label>
              Human side
              <select
                value={humanSide}
                onChange={(e) => setHumanSide(e.target.value)}
                disabled={chatStatus === 'sending' || mode === 'human_vs_human'}
              >
                <option value="white">White</option>
                <option value="black">Black</option>
              </select>
            </label>
            <button type="button" className="btn-send" onClick={startNewGame} disabled={chatStatus === 'sending'}>
              {chatStatus === 'sending' ? 'Working…' : 'New game'}
            </button>

            <div className="warehouse-chat-log">
              <div className="warehouse-chat-item">
                <div className="warehouse-chat-user">Turn: {state.turn}</div>
                <div className="warehouse-chat-assistant">Mode: {state.mode}</div>
              </div>
            </div>

            <form className="warehouse-chat" onSubmit={onSubmit}>
              <h2>Chess chat</h2>
              <textarea
                rows={2}
                placeholder="Examples: e2 to e4, ai move, new game human vs ai"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                disabled={chatStatus === 'sending'}
              />
              <button type="submit" className="btn-send" disabled={chatStatus === 'sending' || !command.trim()}>
                {chatStatus === 'sending' ? 'Sending…' : 'Send'}
              </button>
            </form>

            {chatLog.length > 0 && (
              <div className="warehouse-chat-log">
                {chatLog.slice(-12).map((c) => (
                  <div key={c.id} className="warehouse-chat-item">
                    <div className="warehouse-chat-user">{c.user}</div>
                    <div className="warehouse-chat-assistant">{c.assistant}</div>
                  </div>
                ))}
              </div>
            )}

            <h2>Move history</h2>
            <ul className="warehouse-list">
              {state.move_history.slice(-12).reverse().map((m, idx) => (
                <li key={`${m.from}-${m.to}-${idx}`}>
                  {m.piece} {m.from}-{m.to}
                </li>
              ))}
            </ul>
            {error && (
              <div className="error" role="alert">
                {error}
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  )
}

