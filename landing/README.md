# Groundline landing

The public page in front of the app: what Groundline is, how the pipeline works, why signing in exists, the measured cache numbers, an FAQ, and the privacy and terms pages. Static Astro, English at `/` and Russian at `/ru`. The only client-side JavaScript is Vercel's analytics pair, loaded by `src` from `/_vercel/...` so that the Content-Security-Policy needs no inline-script hashes (see [security notes](../docs/security.md#response-headers)).

```bash
npm install
npm run dev      # http://localhost:4321
npm run build    # dist/
```

## Domains

The landing takes the root domain and the app moves to a subdomain, because the session cookie is `SameSite=Lax` and both must stay under one registrable domain:

| What | Where | Set by |
| --- | --- | --- |
| Landing | `groundline.antonmb.com` | `SITE_URL` (build time, defaults to that) |
| App | `app.groundline.antonmb.com` | `PUBLIC_APP_URL` |
| API | `api.groundline.antonmb.com` | the backend's own `CORS_ORIGINS` and `COOKIE_DOMAIN` |
| Repository links | GitHub | `PUBLIC_REPO_URL` |

Moving the app to `app.` means updating `CORS_ORIGINS=https://app.groundline.antonmb.com` and keeping `COOKIE_DOMAIN=.groundline.antonmb.com` on the backend, and `VITE_API_URL` on the app's Vercel project.

## Deploying to Vercel

A second Vercel project pointing at the same repository:

1. **Add New → Project** → import the repository.
2. **Root Directory**: `landing` (the Astro preset is detected).
3. **Environment Variables**: `SITE_URL`, `PUBLIC_APP_URL`, `PUBLIC_REPO_URL`.
4. **Settings → Domains**: add the root domain.

`robots.txt` names the sitemap by absolute URL, so change it together with `SITE_URL` if the domain differs.

## Screenshots

Three images are referenced and **not yet in the repository**. Until a file exists, the page draws a framed placeholder of the same size carrying the same alt text - nothing breaks, but the page is better with the real thing:

| File | Size | What to capture |
| --- | --- | --- |
| `public/screens/chat.webp` | 1280×800 | Chat with an answer, its sources open, and the pipeline panel showing per-step times |
| `public/screens/limits.webp` | 1280×420 | The service limits bar expanded, with several quotas visible |
| `public/screens/documents.webp` | 1280×800 | Documents: upload area, indexing queue, list of indexed files |

Export as WebP at those exact dimensions (the markup carries `width`/`height`, so the layout does not shift while they load).

## The social image

`public/og.png` (1200×630) is generated, not hand-made:

```bash
node scripts/make-og.mjs
```

Edit the SVG inside that script and rerun it to change the card.

## What is generated

- `/` and `/ru` - the landing in both languages, with `hreflang` pairs and matching canonicals.
- `/privacy`, `/terms` and their `/ru` counterparts.
- `/sitemap.xml` - hand-rolled in `src/pages/sitemap.xml.js`, with `xhtml:link` alternates.
- `/robots.txt`, `/llms.txt` - the second one summarises the project for LLM assistants: what it is, the measured numbers, the seven pipeline steps, and links to every page.

Structured data on the landing: `Organization`, `WebSite`, `SoftwareApplication`, `BreadcrumbList`, `FAQPage`. The legal pages carry `Organization` and `BreadcrumbList`.

## Numbers on the page

Every figure in the "cache numbers" section comes from `MEASURED` in `src/content.js` - a single run against the demo handbook on 2026-09-18, not a projection. Re-measure and update that object rather than editing the copy; the hero facts and `llms.txt` read the same values.
