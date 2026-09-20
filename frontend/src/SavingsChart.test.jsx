import assert from 'node:assert/strict'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { afterEach, beforeEach, test } from 'vitest'
import SavingsChart from './SavingsChart.jsx'
import { LocaleProvider } from './i18n.jsx'

const STATS = { tokens_saved: 849, tokens_used: 1200, cache_hit_rate: 0.5 }

let container
let root

beforeEach(() => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(async () => {
  await act(async () => root.unmount())
  container.remove()
})

async function render(props) {
  await act(async () => {
    root.render(
      <LocaleProvider>
        <SavingsChart {...props} />
      </LocaleProvider>,
    )
  })
  return container
}

test('settled figures carry no pending marker and no indicator', async () => {
  const screen = await render({ stats: STATS })
  const figure = screen.querySelector('.savings-figure')
  assert.ok(figure, 'the figure did not render')
  assert.equal(figure.dataset.pending, undefined)
  assert.equal(screen.querySelector('.panel-head .dot-pulse'), null)
  assert.equal(screen.querySelector('[aria-busy]'), null)
})

test('a refresh dims the figures and shows an indicator next to the heading', async () => {
  const screen = await render({ stats: STATS, pending: true })
  assert.equal(screen.querySelector('.savings-figure').dataset.pending, 'true')
  assert.ok(screen.querySelector('.panel-head .kicker .dot-pulse'), 'no indicator beside the title')
  assert.ok(screen.querySelector('section[aria-busy="true"]'))
})
