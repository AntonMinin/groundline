export const WARN = 0.5
export const CRITICAL = 0.2

export function isDegraded(service) {
  return service.source === 'degraded'
}

export function shareLeft(service) {
  if (!service.limit || service.used === null || service.used === undefined) return null
  return Math.max(0, Math.min(1, (service.limit - service.used) / service.limit))
}

export function stateOf(share) {
  if (share === null) return 'manual'
  if (share < CRITICAL) return 'error'
  if (share < WARN) return 'warn'
  return 'ok'
}

export function worstOf(services) {
  return services
    .map((service) => ({ service, share: shareLeft(service) }))
    .filter((item) => item.share !== null)
    .sort((a, b) => a.share - b.share)[0]
}

export function formatDuration(ms) {
  if (ms === null || ms === undefined) return '—'
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)} s` : `${Math.round(ms)} ms`
}
