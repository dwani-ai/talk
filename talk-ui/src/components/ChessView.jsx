import { useCallback, useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'

const API_BASE = import.meta.env.VITE_API_URL || ''
const SESSION_KEY = 'talk_session_id'
const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const RANKS = ['8', '7', '6', '5', '4', '3', '2', '1']

function squareToWorld(square) {
  const file = square[0]
  const rank = square[1]
  const x = FILES.indexOf(file) - 3.5
  const z = Number(rank) - 4.5
  return [x, z]
}

function PieceModel({ piece }) {
  const kind = piece[1]
  const color = piece.startsWith('w') ? '#e5e7eb' : '#111827'
  const edge = piece.startsWith('w') ? '#1f2937' : '#f3f4f6'
  return (
    <group>
      <mesh castShadow>
        <cylinderGeometry args={[0.25, 0.28, 0.16, 20]} />
        <meshStandardMaterial color={color} />
      </mesh>
      {kind === 'P' && (
        <mesh position={[0, 0.18, 0]} castShadow>
          <sphereGeometry args={[0.11, 20, 20]} />
          <meshStandardMaterial color={edge} />
        </mesh>
      )}
      {kind === 'R' && (
        <mesh position={[0, 0.2, 0]} castShadow>
          <boxGeometry args={[0.24, 0.26, 0.24]} />
          <meshStandardMaterial color={edge} />
        </mesh>
      )}
      {kind === 'N' && (
        <>
          <mesh position={[0, 0.19, 0]} castShadow>
            <coneGeometry args={[0.13, 0.25, 18]} />
            <meshStandardMaterial color={edge} />
          </mesh>
          <mesh position={[0.06, 0.28, 0]} castShadow>
            <sphereGeometry args={[0.06, 16, 16]} />
            <meshStandardMaterial color={edge} />
          </mesh>
        </>
      )}
      {kind === 'B' && (
        <>
          <mesh position={[0, 0.2, 0]} castShadow>
            <coneGeometry args={[0.11, 0.28, 20]} />
            <meshStandardMaterial color={edge} />
          </mesh>
          <mesh position={[0, 0.34, 0]} castShadow>
            <sphereGeometry args={[0.05, 16, 16]} />
            <meshStandardMaterial color={edge} />
          </mesh>
        </>
      )}
      {kind === 'Q' && (
        <>
          <mesh position={[0, 0.21, 0]} castShadow>
            <cylinderGeometry args={[0.09, 0.14, 0.3, 20]} />
            <meshStandardMaterial color={edge} />
          </mesh>
          <mesh position={[0, 0.38, 0]} castShadow>
            <torusGeometry args={[0.07, 0.02, 10, 20]} />
            <meshStandardMaterial color={edge} />
          </mesh>
        </>
      )}
      {kind === 'K' && (
        <>
          <mesh position={[0, 0.22, 0]} castShadow>
            <cylinderGeometry args={[0.09, 0.14, 0.34, 20]} />
            <meshStandardMaterial color={edge} />
          </mesh>
          <mesh position={[0, 0.44, 0]} castShadow>
            <boxGeometry args={[0.04, 0.16, 0.04]} />
            <meshStandardMaterial color={edge} />
          </mesh>
          <mesh position={[0, 0.44, 0]} castShadow>
            <boxGeometry args={[0.14, 0.04, 0.04]} />
            <meshStandardMaterial color={edge} />
          </mesh>
        </>
      )}
    </group>
  )
}

function PieceMesh({ square, piece }) {
  const [x, z] = squareToWorld(square)
  const y = 0.25
  const ref = useRef()
  useFrame((state) => {
    if (!ref.current) return
    ref.current.position.y = y + Math.sin(state.clock.elapsedTime * 2 + x + z) * 0.012
  })
  return (
    <group ref={ref} position={[x, y, z]}>
      <PieceModel piece={piece} />
    </group>
  )
}

function MoveAnimatedPiece({ moveFx, onDone }) {
  const start = squareToWorld(moveFx.from)
  const end = squareToWorld(moveFx.to)
  const ref = useRef()
  const ttl = useRef(0)
  useFrame((_, delta) => {
    ttl.current += delta
    const t = Math.min(1, ttl.current / 0.42)
    if (!ref.current) return
    ref.current.position.x = start[0] + (end[0] - start[0]) * t
    ref.current.position.z = start[1] + (end[1] - start[1]) * t
    ref.current.position.y = 0.25 + Math.sin(t * Math.PI) * 0.16
    if (t >= 1) onDone()
  })
  return (
    <group ref={ref} position={[start[0], 0.25, start[1]]}>
      <PieceModel piece={moveFx.piece} />
    </group>
  )
}

function CinematicCapture({ fx, onDone }) {
  const [x, z] = squareToWorld(fx.square)
  const attackerKind = (fx.attacker && fx.attacker[1]) || 'P'
  const attackerRef = useRef()
  const defenderRef = useRef()
  const ringRef = useRef()
  const flashRef = useRef()
  const sparkRefs = useRef([])
  const ttl = useRef(0)
  const duration = 1.55
  const styleByPiece = {
    P: { ringColor: '#fb923c', flashColor: '#fde68a', sparkColor: '#facc15', impactScale: 1.0 },
    N: { ringColor: '#a78bfa', flashColor: '#ddd6fe', sparkColor: '#c4b5fd', impactScale: 1.1 },
    B: { ringColor: '#22d3ee', flashColor: '#a5f3fc', sparkColor: '#67e8f9', impactScale: 1.05 },
    R: { ringColor: '#f43f5e', flashColor: '#fecdd3', sparkColor: '#fb7185', impactScale: 1.2 },
    Q: { ringColor: '#f59e0b', flashColor: '#fef3c7', sparkColor: '#fbbf24', impactScale: 1.3 },
    K: { ringColor: '#ef4444', flashColor: '#fee2e2', sparkColor: '#f87171', impactScale: 1.35 },
  }
  const style = styleByPiece[attackerKind] || styleByPiece.P

  useFrame((_, delta) => {
    ttl.current += delta
    const t = Math.min(1, ttl.current / duration)
    if (attackerRef.current) {
      if (attackerKind === 'N') {
        const leap = t < 0.55 ? t / 0.55 : 1 - (t - 0.55) / 0.45
        attackerRef.current.position.set(
          x - 0.4 + leap * 0.55,
          0.25 + Math.sin(t * Math.PI) * 0.28,
          z + Math.sin(t * Math.PI * 2.5) * 0.1
        )
        attackerRef.current.rotation.y = 0.25 + leap * 1.35
      } else if (attackerKind === 'B') {
        const slash = t < 0.5 ? t / 0.5 : 1 - (t - 0.5) / 0.5
        attackerRef.current.position.set(
          x - 0.42 + slash * 0.56,
          0.25 + Math.sin(t * Math.PI) * 0.12,
          z - 0.18 + slash * 0.36
        )
        attackerRef.current.rotation.y = 0.75 + slash * 0.6
      } else if (attackerKind === 'R') {
        const ram = t < 0.42 ? t / 0.42 : 1 - (t - 0.42) / 0.58
        attackerRef.current.position.set(x - 0.5 + ram * 0.66, 0.25, z)
        attackerRef.current.rotation.y = ram * 0.22
      } else if (attackerKind === 'Q') {
        const spin = t < 0.5 ? t / 0.5 : 1 - (t - 0.5) / 0.5
        attackerRef.current.position.set(x - 0.4 + spin * 0.55, 0.25 + Math.sin(t * Math.PI) * 0.16, z)
        attackerRef.current.rotation.y = spin * Math.PI * 2.1
      } else if (attackerKind === 'K') {
        const smash = t < 0.48 ? t / 0.48 : 1 - (t - 0.48) / 0.52
        attackerRef.current.position.set(x - 0.46 + smash * 0.6, 0.25 + Math.sin(t * Math.PI) * 0.09, z)
        attackerRef.current.rotation.y = 0.1 + smash * 0.45
      } else {
        const jab = t < 0.45 ? t / 0.45 : 1 - (t - 0.45) / 0.55
        attackerRef.current.position.set(x - 0.38 + jab * 0.48, 0.25 + Math.sin(t * Math.PI) * 0.1, z)
        attackerRef.current.rotation.y = 0.15 + jab * 0.85
      }
    }
    if (defenderRef.current) {
      const impact = t > 0.35 ? (t - 0.35) / 0.65 : 0
      const launch = 0.45 * style.impactScale
      defenderRef.current.position.set(x + 0.12 + impact * launch, 0.25 + Math.sin(t * Math.PI * 4) * 0.04, z)
      defenderRef.current.rotation.z = impact * (1.4 + 0.4 * style.impactScale)
      defenderRef.current.scale.setScalar(1 - impact * 0.6)
    }
    if (ringRef.current) {
      const scale = 0.5 + t * (3.8 + style.impactScale)
      ringRef.current.scale.set(scale, 0.15, scale)
      ringRef.current.material.opacity = Math.max(0, 1 - t * 1.02)
    }
    if (flashRef.current) {
      flashRef.current.material.opacity = Math.max(0, 1 - t * 1.8)
      flashRef.current.scale.setScalar(0.55 + t * 2.2)
    }
    for (let i = 0; i < sparkRefs.current.length; i += 1) {
      const spark = sparkRefs.current[i]
      if (!spark) continue
      const a = (Math.PI * 2 * i) / sparkRefs.current.length
      const speed = (0.5 + (i % 3) * 0.25) * (0.9 + style.impactScale * 0.25)
      const px = x + Math.cos(a) * t * speed
      const pz = z + Math.sin(a) * t * speed
      const py = 0.15 + Math.sin(t * Math.PI) * 0.45
      spark.position.set(px, py, pz)
      spark.material.opacity = Math.max(0, 0.95 - t * 1.35)
    }
    if (t >= 1) onDone()
  })

  return (
    <group>
      <mesh ref={ringRef} position={[x, 0.08, z]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[0.16, 0.3, 28]} />
        <meshBasicMaterial color={style.ringColor} transparent opacity={0.9} />
      </mesh>
      <mesh ref={flashRef} position={[x, 0.22, z]}>
        <sphereGeometry args={[0.18, 20, 20]} />
        <meshBasicMaterial color={style.flashColor} transparent opacity={0.95} />
      </mesh>
      <group ref={attackerRef} position={[x - 0.18, 0.25, z]}>
        <PieceModel piece={fx.attacker || 'wP'} />
      </group>
      <group ref={defenderRef} position={[x + 0.18, 0.25, z]}>
        <PieceModel piece={fx.captured || 'bP'} />
      </group>
      {Array.from({ length: 12 }).map((_, i) => (
        <mesh
          key={`spark-${i}`}
          ref={(el) => {
            sparkRefs.current[i] = el
          }}
          position={[x, 0.2, z]}
        >
          <sphereGeometry args={[0.03, 10, 10]} />
          <meshBasicMaterial color={style.sparkColor} transparent opacity={0.95} />
        </mesh>
      ))}
    </group>
  )
}

function ChessScene({ board, moveFx, clearMoveFx, captureFx, clearCaptureFx }) {
  const pieces = Object.entries(board || {})
  const hideToSquare = moveFx?.to
  const staticPieces = hideToSquare ? pieces.filter(([square]) => square !== hideToSquare) : pieces
  return (
    <Canvas shadows camera={{ position: [0, 7.8, 7.8], fov: 45 }}>
      <color attach="background" args={['#020617']} />
      <ambientLight intensity={0.5} />
      <directionalLight castShadow position={[5, 8, 4]} intensity={1.1} />

      <group>
        {RANKS.flatMap((rank) =>
          FILES.map((file) => {
            const square = `${file}${rank}`
            const [x, z] = squareToWorld(square)
            const dark = (FILES.indexOf(file) + Number(rank)) % 2 === 0
            return (
              <mesh key={square} position={[x, 0, z]} receiveShadow>
                <boxGeometry args={[1, 0.08, 1]} />
                <meshStandardMaterial color={dark ? '#6b4f3a' : '#f2e8cf'} />
              </mesh>
            )
          })
        )}
      </group>

      {staticPieces.map(([square, piece]) => (
        <PieceMesh key={`${piece}-${square}`} square={square} piece={piece} />
      ))}

      {moveFx && <MoveAnimatedPiece moveFx={moveFx} onDone={clearMoveFx} />}
      {captureFx && <CinematicCapture fx={captureFx} onDone={clearCaptureFx} />}

      <OrbitControls maxPolarAngle={Math.PI / 2.05} minDistance={6} maxDistance={14} />
    </Canvas>
  )
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
    last_move: null,
  })
  const [mode, setMode] = useState('human_vs_ai')
  const [humanSide, setHumanSide] = useState('white')
  const [command, setCommand] = useState('')
  const [chatStatus, setChatStatus] = useState('idle')
  const [chatLog, setChatLog] = useState([])
  const [error, setError] = useState(null)
  const [captureFx, setCaptureFx] = useState(null)
  const [pendingCaptureFx, setPendingCaptureFx] = useState(null)
  const [moveFx, setMoveFx] = useState(null)
  const historyLenRef = useRef(0)

  const applyState = useCallback((data) => {
    if (!data || typeof data !== 'object') return
    const history = Array.isArray(data.move_history) ? data.move_history : []
    if (history.length < historyLenRef.current) {
      historyLenRef.current = 0
    }
    const newMoves = history.slice(historyLenRef.current)
    if (newMoves.length > 0) {
      const latest = newMoves[newMoves.length - 1]
      if (latest?.from && latest?.to) {
        setMoveFx({
          from: latest.from,
          to: latest.to,
          piece: (data.board && data.board[latest.to]) || latest.piece || 'wP',
        })
      }
      const capturedMove = [...newMoves].reverse().find((m) => Boolean(m?.captured))
      if (capturedMove) {
        setPendingCaptureFx({
          square: capturedMove.to,
          captured: capturedMove.captured,
          attacker: capturedMove.piece || 'wP',
        })
      }
    }
    historyLenRef.current = history.length
    setState({
      board: data.board || {},
      turn: data.turn || 'white',
      mode: data.mode || 'human_vs_ai',
      status: data.status || 'in_progress',
      move_history: history,
      human_side: data.human_side || 'white',
      last_move: data.last_move || null,
    })
  }, [])

  useEffect(() => {
    if (!moveFx && pendingCaptureFx && !captureFx) {
      setCaptureFx(pendingCaptureFx)
      setPendingCaptureFx(null)
    }
  }, [moveFx, pendingCaptureFx, captureFx])

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
    const poll = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      fetchState()
    }
    const id = setInterval(poll, 1200)
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

        <div className="warehouse-layout">
          <div className="warehouse-canvas chess-board-wrap">
            <ChessScene
              board={state.board}
              moveFx={moveFx}
              clearMoveFx={() => setMoveFx(null)}
              captureFx={captureFx}
              clearCaptureFx={() => setCaptureFx(null)}
            />
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

