import { fetchJson } from './http'

export async function getCurrentUser() {
  return await fetchJson('/v1/auth/me')
}

export async function signup({ email, password }) {
  return await fetchJson('/v1/auth/signup', {
    method: 'POST',
    body: { email, password },
  })
}

export async function login({ email, password }) {
  return await fetchJson('/v1/auth/login', {
    method: 'POST',
    body: { email, password },
  })
}

export async function logout() {
  return await fetchJson('/v1/auth/logout', { method: 'POST' })
}

