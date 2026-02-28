import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

function renderApp() {
  return render(
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
}

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn())
    localStorage.clear()
    sessionStorage.clear()
  })

  it('renders header and main UI', () => {
    renderApp()
    expect(screen.getByRole('heading', { name: /dwani\.ai/i })).toBeInTheDocument()
    expect(screen.getByText(/Hold to talk/i)).toBeInTheDocument()
  })

  it('shows language selector', () => {
    renderApp()
    expect(screen.getByRole('combobox', { name: /language/i })).toBeInTheDocument()
  })

  it('shows mode selector', () => {
    renderApp()
    const modeSelect = screen.getByRole('combobox', { name: /mode/i })
    expect(modeSelect).toBeInTheDocument()
  })

  it('has New conversation in footer', () => {
    renderApp()
    expect(screen.getByRole('button', { name: /new conversation/i })).toBeInTheDocument()
  })
})
