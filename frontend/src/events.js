import { BASE_URL } from './api.js'

const TYPES = ['connected', 'node_started', 'node_finished', 'ingest', 'limits', 'error']

let source = null
const listeners = new Set()

function dispatch(message) {
  let event
  try {
    event = JSON.parse(message.data)
  } catch {
    return
  }
  listeners.forEach((listener) => listener(event))
}

export function connectEvents() {
  if (source) return
  source = new EventSource(`${BASE_URL}/events`, { withCredentials: true })
  source.onmessage = dispatch
  TYPES.forEach((type) => source.addEventListener(type, dispatch))
}

export function disconnectEvents() {
  source?.close()
  source = null
}

export function onEvent(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
