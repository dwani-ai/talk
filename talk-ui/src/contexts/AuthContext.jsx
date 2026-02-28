import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest, signup as signupRequest } from '../lib/authClient'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const user = await getCurrentUser()
      setCurrentUser(user || null)
    } catch (_) {
      setCurrentUser(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
  }, [refresh])

  const signup = useCallback(async ({ email, password }) => {
    const user = await signupRequest({ email, password })
    setCurrentUser(user || null)
    return user
  }, [])

  const login = useCallback(async ({ email, password }) => {
    const user = await loginRequest({ email, password })
    setCurrentUser(user || null)
    return user
  }, [])

  const logout = useCallback(async () => {
    await logoutRequest()
    setCurrentUser(null)
  }, [])

  const value = useMemo(
    () => ({
      currentUser,
      isAuthenticated: Boolean(currentUser),
      isLoading,
      refresh,
      signup,
      login,
      logout,
    }),
    [currentUser, isLoading, refresh, signup, login, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}
