import { BASE_URL } from './api.js'

const TYPES = ['connected', 'node_started', 'node_finished', 'ingest', 'limits', 'error']
const RETRY_MS = 5000

let source = null
let retry = null
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
  source.onerror = () => {
    if (source?.readyState !== EventSource.CLOSED) return
    source = null
    clearTimeout(retry)
    retry = setTimeout(connectEvents, RETRY_MS)
  }
}

export function disconnectEvents() {
  clearTimeout(retry)
  retry = null
  source?.close()
  source = null
}

export function onEvent(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
