import { useEffect, useState, useCallback, useRef } from 'react'
import { NavLink } from 'react-router-dom'
import { Canvas, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'

const API_BASE = import.meta.env.VITE_API_URL || ''

const SESSION_KEY = 'talk_session_id'

function getOrCreateSessionId() {
  let id = sessionStorage.getItem(SESSION_KEY)
  if (!id) {
    id = crypto.randomUUID?.() || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`
    sessionStorage.setItem(SESSION_KEY, id)
  }
  return id
}

const LERP_SPEED = 5

function Robot({ robot }) {
  if (!robot) return null
  const [tx, ty, tz] = robot.position || [0, 0, 0]
  const type = robot.type
  const color = type === 'uav' ? '#38bdf8' : type === 'ugv' ? '#22c55e' : '#f97316'
  const scale =
    type === 'uav'
      ? [0.8, 0.2, 0.8]
      : type === 'ugv'
        ? [1.0, 0.4, 1.4]
        : [0.5, 1.2, 0.5]

  const groupRef = useRef()
  const posRef = useRef([tx, ty, tz])

  useFrame((_, delta) => {
    if (!groupRef.current) return
    const t = Math.min(1, delta * LERP_SPEED)
    posRef.current[0] += (tx - posRef.current[0]) * t
    posRef.current[1] += (ty - posRef.current[1]) * t
    posRef.current[2] += (tz - posRef.current[2]) * t
    groupRef.current.position.set(posRef.current[0], posRef.current[1], posRef.current[2])
  })

  return (
    <group ref={groupRef}>
      <mesh>
        <boxGeometry args={scale} />
        <meshStandardMaterial color={color} />
      </mesh>
    </group>
  )
}

function Item({ item }) {
  if (!item) return null
  const [tx, ty, tz] = item.position || [0, 0, 0]
  const meshRef = useRef()
  const posRef = useRef([tx, ty + 0.25, tz])

  useFrame((_, delta) => {
    if (!meshRef.current) return
    const t = Math.min(1, delta * LERP_SPEED)
    posRef.current[0] += (tx - posRef.current[0]) * t
    posRef.current[1] += (ty + 0.25 - posRef.current[1]) * t
    posRef.current[2] += (tz - posRef.current[2]) * t
    meshRef.current.position.set(posRef.current[0], posRef.current[1], posRef.current[2])
  })

  return (
    <mesh ref={meshRef}>
      <boxGeometry args={[0.5, 0.5, 0.5]} />
      <meshStandardMaterial color={item.stack_id ? '#eab308' : '#a855f7'} />
    </mesh>
  )
}

export default function WarehouseView() {
  const [state, setState] = useState({ warehouse: null, robots: [], items: [] })
  const [error, setError] = useState(null)
  const [sessionId] = useState(() => getOrCreateSessionId())
  const [command, setCommand] = useState('')
  const [chatStatus, setChatStatus] = useState('idle')
  const [chatLog, setChatLog] = useState([])

  const fetchState = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/v1/warehouse/state`)
      if (!res.ok) {
        throw new Error(`Server error ${res.status}`)
      }
      const data = await res.json()
      setState({
        warehouse: data.warehouse || null,
        robots: data.robots || [],
        items: data.items || [],
      })
      setError(null)
    } catch (e) {
      setError(e.message || 'Failed to load warehouse state')
    }
  }, [])

  useEffect(() => {
    fetchState()
    const poll = () => {
      if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return
      fetchState()
    }
    const id = setInterval(poll, 1000)
    return () => {
      clearInterval(id)
    }
  }, [fetchState])

  const sendCommand = useCallback(
    async (e) => {
      e.preventDefault()
      const text = command.trim()
      if (!text || chatStatus === 'sending') return

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
            text,
            mode: 'agent',
            agent_name: 'warehouse_orchestrator',
          }),
        })
        if (!res.ok) {
          const err = await res.json().catch(() => ({}))
          throw new Error(err.detail || `Server error ${res.status}`)
        }
        const data = await res.json()
        const assistant = data.reply || '(no response)'
        setChatLog((prev) => [
          ...prev,
          {
            id: Date.now(),
            user: text,
            assistant,
          },
        ])
        // Apply verified warehouse state from response so 3D view updates immediately
        if (data.warehouse_state && typeof data.warehouse_state === 'object') {
          const ws = data.warehouse_state
          setState({
            warehouse: ws.warehouse ?? null,
            robots: Array.isArray(ws.robots) ? ws.robots : [],
            items: Array.isArray(ws.items) ? ws.items : [],
          })
        } else {
          await fetchState()
          setTimeout(fetchState, 400)
        }
        setCommand('')
        setChatStatus('idle')
      } catch (e) {
        setError(e.message || 'Command failed')
        setChatStatus('idle')
      }
    },
    [command, chatStatus, sessionId, fetchState]
  )

  const { warehouse, robots, items } = state
  const uav = robots.find((r) => r.type === 'uav')
  const ugv = robots.find((r) => r.type === 'ugv')
  const arm = robots.find((r) => r.type === 'arm')

  return (
    <div className="app">
      <main className="main warehouse-main">
        <header>
          <div className="header-main">
            <div>
              <h1>Warehouse robots</h1>
              <p className="tagline">Live 3D view of UAV, UGV, and arm state. Commands (e.g. ugv pick item-1) run via the agent and update the view.</p>
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
          <div className="warehouse-canvas">
            <button
              type="button"
              className="warehouse-refresh"
              onClick={fetchState}
              title="Refresh 3D view"
              aria-label="Refresh 3D view"
            >
              ↻ Refresh
            </button>
            <Canvas camera={{ position: [20, 25, 30], fov: 45 }}>
              <color attach="background" args={['#020617']} />
              <ambientLight intensity={0.4} />
              <directionalLight position={[10, 20, 10]} intensity={0.8} />

              <Grid
                args={[warehouse?.width || 50, warehouse?.depth || 30]}
                cellSize={1}
                sectionSize={5}
                cellThickness={0.3}
                sectionThickness={1}
                fadeDistance={40}
              />

              <Robot robot={uav} />
              <Robot robot={ugv} />
              <Robot robot={arm} />

              {items.map((it) => (
                <Item key={it.id} item={it} />
              ))}

              <OrbitControls makeDefault />
            </Canvas>
          </div>

          <aside className="warehouse-sidebar">
            <form className="warehouse-chat" onSubmit={sendCommand}>
              <h2>Command robots</h2>
              <textarea
                rows={2}
                placeholder="Tell the warehouse agent what to do (e.g. move ugv north, pick item-1, move towards arm)…"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                disabled={chatStatus === 'sending'}
              />
              <button
                type="submit"
                className="btn-send"
                disabled={chatStatus === 'sending' || !command.trim()}
              >
                {chatStatus === 'sending' ? 'Sending…' : 'Send'}
              </button>
            </form>

            {chatLog.length > 0 && (
              <div className="warehouse-chat-log">
                {chatLog.map((c) => (
                  <div key={c.id} className="warehouse-chat-item">
                    <div className="warehouse-chat-user">{c.user}</div>
                    <div className="warehouse-chat-assistant">{c.assistant}</div>
                  </div>
                ))}
              </div>
            )}

            <h2>Robots</h2>
            <ul className="warehouse-list">
              {robots.map((r) => (
                <li key={r.id}>
                  <strong>{r.id}</strong> · {r.type} · status {r.status}
                </li>
              ))}
            </ul>
            <h2>Items</h2>
            <ul className="warehouse-list">
              {items.map((it) => (
                <li key={it.id}>
                  <strong>{it.id}</strong>{' '}
                  {it.stack_id ? `(stack ${it.stack_id})` : '(loose on floor)'}
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

