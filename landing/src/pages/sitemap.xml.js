import { UPDATED } from '../legal.js'

const PAGES = [
  { path: '/', priority: '1.0' },
  { path: '/ru', priority: '1.0' },
  { path: '/privacy', priority: '0.3' },
  { path: '/ru/privacy', priority: '0.3' },
  { path: '/terms', priority: '0.3' },
  { path: '/ru/terms', priority: '0.3' },
]

const alternatesFor = (path, origin) => {
  const bare = path.replace(/^\/ru/, '') || '/'
  return [
    { hreflang: 'en', href: new URL(bare, origin).href },
    { hreflang: 'ru', href: new URL('/ru' + (bare === '/' ? '' : bare), origin).href },
  ]
}

export function GET({ site }) {
  const origin = site ?? new URL('https://groundline.antonmb.com')
  const urls = PAGES.map(({ path, priority }) => {
    const links = alternatesFor(path, origin)
      .map((link) => `    <xhtml:link rel="alternate" hreflang="${link.hreflang}" href="${link.href}"/>`)
      .join('\n')
    return [
      '  <url>',
      `    <loc>${new URL(path, origin).href}</loc>`,
      `    <lastmod>${UPDATED}</lastmod>`,
      `    <priority>${priority}</priority>`,
      links,
      '  </url>',
    ].join('\n')
  }).join('\n')

  const body = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
${urls}
</urlset>
`
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } })
}
