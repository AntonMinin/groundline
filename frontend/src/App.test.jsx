import assert from 'node:assert/strict'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, expect, test, vi } from 'vitest'
import App from './App.jsx'
import { LocaleProvider } from './i18n.jsx'
import { api } from './api.js'
import { BOOT_STEPS } from './session.js'

vi.mock('./events.js', () => ({
  connectEvents: vi.fn(),
  disconnectEvents: vi.fn(),
  onEvent: () => () => {},
}))

const SESSION_KEY = 'groundline.session'

const account = (termsRequired) => ({
  id: 'e1a7f0c2-0000-4000-8000-000000000000',
  email: 'reader@example.com',
  created_at: '2026-09-01T10:00:00Z',
  terms_required: termsRequired,
})

function stubApi() {
  const calls = []
  const record = (step, value) =>
    vi.spyOn(api, step).mockImplementation(async () => {
      calls.push(step)
      return value
    })
  record('me', account(false))
  record('limits', { services: [], degraded: false, checked_at: null })
  record('stats', { total_queries: 0, limits: { max_documents: 1, max_upload_mb: 0.3 } })
  record('documents', [])
  record('history', [])
  vi.spyOn(api, 'config').mockResolvedValue({ turnstile_site_key: '' })
  return calls
}

const unique = (calls) => [...new Set(calls)].sort()

let container
let root

beforeEach(() => {
  Element.prototype.scrollIntoView = () => {}
  localStorage.clear()
  container = document.createElement('div')
  document.body.append(container)
})

afterEach(async () => {
  await act(async () => root?.unmount())
  container.remove()
})

async function render() {
  root = createRoot(container)
  await act(async () => {
    root.render(
      <LocaleProvider>
        <App />
      </LocaleProvider>,
    )
  })
  return container
}

test('without a session the login screen is shown and nothing is requested', async () => {
  const calls = stubApi()
  const screen = await render()

  assert.deepEqual(calls, [], 'boot endpoints were called for a signed-out visitor')
  for (const step of BOOT_STEPS) {
    expect(api[step]).not.toHaveBeenCalled()
  }
  assert.ok(screen.querySelector('input[type="email"]'), 'no email field, so this is not the login screen')
  assert.ok(screen.textContent.includes('Why sign in'))
})

test('with a session whose terms are out of date the consent screen is shown', async () => {
  const calls = stubApi()
  api.me.mockImplementation(async () => {
    calls.push('me')
    return account(true)
  })
  localStorage.setItem(SESSION_KEY, '1')

  const screen = await render()

  assert.deepEqual(unique(calls), [...BOOT_STEPS].sort())
  assert.ok(screen.textContent.includes('The terms have changed'))
  assert.ok(screen.querySelector('input[type="checkbox"][required]'), 'consent box is not required')
  assert.ok(!screen.querySelector('.app-tabs'), 'the application is reachable before accepting')
})

test('with a session and current terms the data is loaded and the app is shown', async () => {
  const calls = stubApi()
  localStorage.setItem(SESSION_KEY, '1')

  const screen = await render()

  assert.deepEqual(unique(calls), [...BOOT_STEPS].sort())
  assert.ok(screen.querySelector('.app-tabs'), 'the application shell did not render')
  assert.ok(screen.textContent.includes('reader@example.com'))
})

test('a 401 during boot drops the session hint and returns to the login screen', async () => {
  stubApi()
  api.stats.mockRejectedValue(Object.assign(new Error('Not authenticated'), { status: 401 }))
  localStorage.setItem(SESSION_KEY, '1')

  const screen = await render()

  assert.equal(localStorage.getItem(SESSION_KEY), null, 'the session hint survived a 401')
  assert.ok(screen.querySelector('input[type="email"]'))
})
