import { useState } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'

export default function AuthPage({ mode }) {
  const isSignup = mode === 'signup'
  const navigate = useNavigate()
  const { login, signup, isLoading } = useAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [status, setStatus] = useState('idle')
  const [error, setError] = useState(null)

  const onSubmit = async (e) => {
    e.preventDefault()
    if (status === 'submitting') return
    setStatus('submitting')
    setError(null)
    try {
      if (isSignup) {
        await signup({ email, password })
      } else {
        await login({ email, password })
      }
      navigate('/')
    } catch (err) {
      setError(err.message || 'Request failed')
    } finally {
      setStatus('idle')
    }
  }

  return (
    <div className="app">
      <main className="main auth-main">
        <header>
          <div className="header-main">
            <div>
              <h1>dwani.ai</h1>
              <p className="tagline">Optional account login for persistent identity.</p>
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

        <form className="auth-card" onSubmit={onSubmit}>
          <h2>{isSignup ? 'Create account' : 'Log in'}</h2>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
              disabled={isLoading || status === 'submitting'}
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={isSignup ? 'new-password' : 'current-password'}
              minLength={8}
              required
              disabled={isLoading || status === 'submitting'}
            />
          </label>
          <button type="submit" className="btn-send" disabled={isLoading || status === 'submitting'}>
            {status === 'submitting' ? 'Please wait…' : isSignup ? 'Sign up' : 'Log in'}
          </button>

          {error && (
            <div className="error" role="alert">
              <span>{error}</span>
            </div>
          )}

          <p className="auth-switch">
            {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
            <Link to={isSignup ? '/login' : '/signup'}>{isSignup ? 'Log in' : 'Sign up'}</Link>
          </p>
        </form>
      </main>
    </div>
  )
}
