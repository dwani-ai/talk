import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'

const API_BASE = import.meta.env.VITE_API_URL || ''

function Robot({ robot }) {
  if (!robot) return null
  const [x, y, z] = robot.position || [0, 0, 0]
  const type = robot.type
  const color = type === 'uav' ? '#38bdf8' : type === 'ugv' ? '#22c55e' : '#f97316'
  const scale =
    type === 'uav'
      ? [0.8, 0.2, 0.8]
      : type === 'ugv'
        ? [1.0, 0.4, 1.4]
        : [0.5, 1.2, 0.5]

  return (
    <group position={[x, y, z]}>
      <mesh>
        <boxGeometry args={scale} />
        <meshStandardMaterial color={color} />
      </mesh>
    </group>
  )
}

function Item({ item }) {
  if (!item) return null
  const [x, y, z] = item.position || [0, 0, 0]
  return (
    <mesh position={[x, y + 0.25, z]}>
      <boxGeometry args={[0.5, 0.5, 0.5]} />
      <meshStandardMaterial color={item.stack_id ? '#eab308' : '#a855f7'} />
    </mesh>
  )
}

export default function WarehouseView() {
  const [state, setState] = useState({ warehouse: null, robots: [], items: [] })
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false

    async function fetchState() {
      try {
        const res = await fetch(`${API_BASE}/v1/warehouse/state`)
        if (!res.ok) {
          throw new Error(`Server error ${res.status}`)
        }
        const data = await res.json()
        if (!cancelled) {
          setState({
            warehouse: data.warehouse || null,
            robots: data.robots || [],
            items: data.items || [],
          })
          setError(null)
        }
      } catch (e) {
        if (!cancelled) {
          setError(e.message || 'Failed to load warehouse state')
        }
      }
    }

    fetchState()
    const id = setInterval(fetchState, 2000)
    return () => {
      cancelled = true
      clearInterval(id)
    }
  }, [])

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
              <p className="tagline">Live 3D view of UAV, UGV, and arm state.</p>
            </div>
            <nav className="nav-tabs">
              <Link to="/" className="nav-tab">
                Talk
              </Link>
              <Link to="/warehouse" className="nav-tab">
                Warehouse
              </Link>
            </nav>
          </div>
        </header>

        <div className="warehouse-layout">
          <div className="warehouse-canvas">
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

