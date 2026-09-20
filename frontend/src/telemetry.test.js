import assert from 'node:assert/strict'
import { test } from 'vitest'
import { formatDuration, isDegraded, shareLeft, stateOf, worstOf } from './telemetry.js'

const quota = (used, limit) => ({ key: `q${used}`, service: 'Groq', used, limit })

test('share left is the remaining fraction, clamped', () => {
  assert.equal(shareLeft(quota(0, 100)), 1)
  assert.equal(shareLeft(quota(75, 100)), 0.25)
  assert.equal(shareLeft(quota(130, 100)), 0)
})

test('services the application does not meter have no share', () => {
  assert.equal(shareLeft({ used: null, limit: 750 }), null)
  assert.equal(shareLeft({ used: 5, limit: null }), null)
})

test('colours follow the thresholds: green above 50%, yellow 20-50%, red below 20%', () => {
  assert.equal(stateOf(1), 'ok')
  assert.equal(stateOf(0.5), 'ok')
  assert.equal(stateOf(0.49), 'warn')
  assert.equal(stateOf(0.2), 'warn')
  assert.equal(stateOf(0.19), 'error')
  assert.equal(stateOf(0), 'error')
  assert.equal(stateOf(null), 'manual')
})

test('the bar reports the quota closest to its limit and ignores unmetered ones', () => {
  const services = [quota(10, 100), quota(90, 100), { used: null, limit: 750 }, quota(50, 100)]
  assert.equal(worstOf(services).service.used, 90)
  assert.equal(worstOf([{ used: null, limit: 750 }]), undefined)
})

test('a degraded counter is not a healthy zero', () => {
  const broken = { service: 'Groq', source: 'degraded', used: null, limit: 1000 }
  assert.equal(isDegraded(broken), true)
  assert.equal(shareLeft(broken), null)
  assert.equal(isDegraded({ source: 'local', used: 0, limit: 1000 }), false)
  assert.equal(worstOf([broken]), undefined)
})

test('durations switch to seconds at one second', () => {
  assert.equal(formatDuration(940), '940 ms')
  assert.equal(formatDuration(1910), '1.91 s')
  assert.equal(formatDuration(undefined), '-')
})
