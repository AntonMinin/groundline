export const BASE_URL = (import.meta.env.VITE_API_URL || '/api').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

async function errorMessage(response) {
  try {
    const { detail } = await response.json()
    return typeof detail === 'string' ? detail : detail.map((item) => item.msg).join(', ')
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

async function request(path, { method = 'GET', json, body } = {}) {
  const headers = { 'X-Requested-With': 'groundline' }
  if (json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(json)
  }
  const response = await fetch(`${BASE_URL}${path}`, { method, headers, body, credentials: 'include' })
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  return response
}

async function* parseEvents(response) {
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) return
    buffer += value
    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = block
        .split('\n')
        .filter((line) => line.startsWith('data: '))
        .map((line) => line.slice(6))
        .join('\n')
      if (data) yield JSON.parse(data)
    }
  }
}

export const api = {
  requestOtp: (email) => request('/auth/request-otp', { method: 'POST', json: { email } }),
  verifyOtp: (email, code) => request('/auth/verify-otp', { method: 'POST', json: { email, code } }).then((r) => r.json()),
  logout: () => request('/auth/logout', { method: 'POST' }),
  me: () => request('/me').then((r) => r.json()),
  deleteAccount: () => request('/me', { method: 'DELETE' }),
  stats: () => request('/stats').then((r) => r.json()),
  documents: () => request('/documents').then((r) => r.json()),
  upload: (file) => {
    const form = new FormData()
    form.append('file', file)
    return request('/ingest', { method: 'POST', body: form }).then((r) => r.json())
  },
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),
  deleteAllDocuments: () => request('/documents', { method: 'DELETE' }),
  clearCache: () => request('/cache', { method: 'DELETE' }),
  clearHistory: () => request('/history', { method: 'DELETE' }),
  history: (limit = 20) => request(`/history?limit=${limit}`).then((r) => r.json()),
  async *query(question) {
    const response = await request('/query', { method: 'POST', json: { question } })
    yield* parseEvents(response)
  },
}
