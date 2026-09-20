import { createHash } from 'node:crypto'
import { readFileSync, readdirSync, writeFileSync, existsSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const CSP_HEADER = 'Content-Security-Policy'

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..')
const FONT_STYLES = 'https://fonts.googleapis.com'
const FONT_FILES = 'https://fonts.gstatic.com'
const TURNSTILE = 'https://challenges.cloudflare.com'

export const apiOrigin = () => new URL(process.env.VITE_API_URL || 'https://api.groundline.antonmb.com').origin

const serialise = (directives) =>
  Object.entries(directives)
    .map(([name, values]) => `${name} ${values.join(' ')}`)
    .join('; ')

export const landingPolicy = (scriptHashes = []) =>
  serialise({
    'default-src': ["'self'"],
    'script-src': ["'self'", ...scriptHashes],
    'style-src': ["'self'", "'unsafe-inline'", FONT_STYLES],
    'img-src': ["'self'", 'data:'],
    'font-src': ["'self'", FONT_FILES],
    'connect-src': ["'self'"],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
  })

export const appPolicy = () =>
  serialise({
    'default-src': ["'self'"],
    'script-src': ["'self'", TURNSTILE],
    'style-src': ["'self'", "'unsafe-inline'", FONT_STYLES],
    'img-src': ["'self'", 'data:'],
    'font-src': ["'self'", FONT_FILES],
    'connect-src': ["'self'", apiOrigin(), TURNSTILE],
    'frame-src': [TURNSTILE],
    'object-src': ["'none'"],
    'base-uri': ["'self'"],
    'form-action': ["'self'"],
    'frame-ancestors': ["'none'"],
  })

const htmlFiles = (directory) => {
  if (!existsSync(directory)) return []
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const full = join(directory, entry.name)
    if (entry.isDirectory()) return htmlFiles(full)
    return entry.name.endsWith('.html') ? [full] : []
  })
}

const INLINE_SCRIPT = /<script(?![^>]*\ssrc=)([^>]*)>([\s\S]*?)<\/script>/gi
const EXECUTABLE = /^(?:\s*|[^>]*type="(?:module|text\/javascript|application\/javascript)"[^>]*)$/i

export const inlineScriptHashes = (distDirectory) => {
  const hashes = new Set()
  for (const file of htmlFiles(distDirectory)) {
    for (const [, attributes, body] of readFileSync(file, 'utf8').matchAll(INLINE_SCRIPT)) {
      if (!EXECUTABLE.test(attributes) || !body.trim()) continue
      hashes.add(`'sha256-${createHash('sha256').update(body, 'utf8').digest('base64')}'`)
    }
  }
  return [...hashes].sort()
}

export const headersFor = (policy) => [
  { key: 'X-Content-Type-Options', value: 'nosniff' },
  { key: 'X-Frame-Options', value: 'DENY' },
  { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
  {
    key: 'Permissions-Policy',
    value: 'camera=(), microphone=(), geolocation=(), payment=(), interest-cohort=()',
  },
  { key: CSP_HEADER, value: policy },
]

export const vercelConfig = (policy) => ({
  headers: [{ source: '/(.*)', headers: headersFor(policy) }],
})

const write = (project, policy) => {
  const target = join(ROOT, project, 'vercel.json')
  writeFileSync(target, `${JSON.stringify(vercelConfig(policy), null, 2)}\n`, 'utf8')
  return target
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const hashes = inlineScriptHashes(join(ROOT, 'landing', 'dist'))
  if (hashes.length === 0) {
    console.warn('no inline scripts found in landing/dist - build the landing first, or it genuinely has none')
  }
  console.log(write('frontend', appPolicy()), `connect-src includes ${apiOrigin()}`)
  console.log(write('landing', landingPolicy(hashes)), `${hashes.length} inline script hash(es)`)
}
