import { BASE_URL } from './api.js'

let source = null
const listeners = new Set()

export function connectEvents() {
  if (source) return
  source = new EventSource(`${BASE_URL}/events`, { withCredentials: true })
  source.onmessage = (message) => {
    let event
    try {
      event = JSON.parse(message.data)
    } catch {
      return
    }
    listeners.forEach((listener) => listener(event))
  }
}

export function disconnectEvents() {
  source?.close()
  source = null
}

export function onEvent(listener) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}
