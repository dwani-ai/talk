import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
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
    expect(screen.getByRole('button', { name: /^new conversation$/i })).toBeInTheDocument()
  })

  it('sends typed chat message and renders reply', async () => {
    global.fetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ reply: 'hello back' }),
    })

    renderApp()
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), {
      target: { value: 'hello' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByText('hello back')).toBeInTheDocument()
    })
  })

  it('shows retry after failed request', async () => {
    global.fetch.mockRejectedValueOnce(new Error('network down'))

    renderApp()
    fireEvent.change(screen.getByPlaceholderText(/type your message/i), {
      target: { value: 'hello' },
    })
    fireEvent.click(screen.getByRole('button', { name: /send/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument()
    })
  })
})
