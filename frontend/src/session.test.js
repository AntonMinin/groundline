import assert from 'node:assert/strict'
import { test } from 'vitest'
import { BOOT_STEPS, boot } from './session.js'

function fakeApi(handler = async () => ({})) {
  const calls = []
  const api = {}
  for (const step of BOOT_STEPS) {
    api[step] = () => {
      calls.push(step)
      return handler(step)
    }
  }
  return { api, calls }
}

const unauthorized = () => Object.assign(new Error('Not authenticated'), { status: 401 })

test('without a session nothing is requested at all', async () => {
  const { api, calls } = fakeApi()
  const result = await boot(api, { signedIn: false })
  assert.equal(result, null)
  assert.deepEqual(calls, [])
})

test('localStorage being unavailable counts as no session', async () => {
  const { api, calls } = fakeApi()
  assert.equal(await boot(api), null)
  assert.deepEqual(calls, [])
})

test('with a session every step is requested once and returned', async () => {
  const { api, calls } = fakeApi(async (step) => `${step}-payload`)
  const result = await boot(api, { signedIn: true })
  assert.deepEqual(calls.sort(), [...BOOT_STEPS].sort())
  assert.deepEqual(result.data, Object.fromEntries(BOOT_STEPS.map((step) => [step, `${step}-payload`])))
})

test('a 401 from any step drops the session and is not retried', async () => {
  for (const failing of BOOT_STEPS) {
    const { api, calls } = fakeApi(async (step) => {
      if (step === failing) throw unauthorized()
      return step
    })
    const result = await boot(api, { signedIn: true })
    assert.equal(result.unauthorized, true, `${failing} should end the session`)
    assert.equal(result.data, undefined)
    assert.equal(calls.length, BOOT_STEPS.length, `${failing} triggered a retry`)
  }
})

test('a failure that is not a 401 leaves the session and yields null for that step', async () => {
  const { api } = fakeApi(async (step) => {
    if (step === 'history') throw Object.assign(new Error('gateway'), { status: 502 })
    return step
  })
  const result = await boot(api, { signedIn: true })
  assert.equal(result.unauthorized, undefined)
  assert.equal(result.data.history, null)
  assert.equal(result.data.me, 'me')
})

test('progress is reported per step, only for the ones that arrived', async () => {
  const seen = []
  const { api } = fakeApi(async (step) => {
    if (step === 'stats') throw unauthorized()
    return step
  })
  await boot(api, { signedIn: true, onLoaded: (step) => seen.push(step) })
  assert.ok(!seen.includes('stats'))
  assert.equal(seen.length, BOOT_STEPS.length - 1)
})
