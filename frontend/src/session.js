const KEY = 'groundline.session'

export const BOOT_STEPS = ['me', 'limits', 'stats', 'documents', 'history']

export function hasSession() {
  try {
    return localStorage.getItem(KEY) === '1'
  } catch {
    return false
  }
}

export function rememberSession() {
  try {
    localStorage.setItem(KEY, '1')
  } catch {}
}

export function forgetSession() {
  try {
    localStorage.removeItem(KEY)
  } catch {}
}

export async function boot(api, { onLoaded = () => {}, signedIn = hasSession() } = {}) {
  if (!signedIn) return null

  const settled = await Promise.all(
    BOOT_STEPS.map((step) =>
      api[step]().then(
        (value) => {
          onLoaded(step)
          return { value }
        },
        (error) => ({ error }),
      ),
    ),
  )

  if (settled.some(({ error }) => error?.status === 401)) {
    forgetSession()
    return { unauthorized: true }
  }

  return { data: Object.fromEntries(BOOT_STEPS.map((step, index) => [step, settled[index].value ?? null])) }
}
