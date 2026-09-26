# Security notes

What is defended, how, and what is deliberately left out.

## Tenant isolation

Isolation is enforced twice, independently.

**1. In the application.** Every query filters by `user_id`, and every path that touches tenant data goes through `tenant_session(user_id)`.

**2. In the database.** `documents`, `chunks`, `query_cache`, `query_log` and `ingest_jobs` have:

```sql
ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;
ALTER TABLE <table> FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON <table>
  USING (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid)
  WITH CHECK (user_id = NULLIF(current_setting('app.user_id', true), '')::uuid);
```

`app.user_id` is set with `set_config(..., true)` - transaction-local - by an `after_begin` listener in `app/db/session.py`, so it is bound to the transaction and cannot leak to the next borrower of a pooled connection. `USING` blocks reads and `WITH CHECK` blocks writes, so a forgotten filter cannot read *or* create another user's rows. Without the setting, the policy matches nothing and queries return empty rather than everything.

This only works while the application connects as a role **without** `BYPASSRLS`. The migration grants the application role table privileges explicitly and, on Supabase, revokes access from the `anon` and `authenticated` roles so the tables are not exposed through the Supabase Data API. Running the app as `postgres` or any superuser silently removes this entire layer.

`tests/test_isolation.py` runs against the restricted role and asserts that a second user cannot find, list, delete or insert rows even with deliberately unfiltered queries.

**Tables that must *not* have RLS.** `users` and `otp_codes` are reached through the authentication path, before any user identity exists, so there is no `app.user_id` to match a policy against; `alembic_version` belongs to the migration role alone. On a platform that enables row-level security automatically for every new table in `public` - Supabase does - those tables end up with RLS on and **no policy**, which in Postgres means the application role sees zero rows and login stops working. Migration `0005` turns RLS off on them explicitly and re-revokes `anon`/`authenticated`, so the Supabase Data API still cannot reach them. `tests/test_isolation.py` asserts the invariant for every table in `public`: either RLS with a policy, or no RLS - a table with RLS and no policy fails the suite. Add a new tenant table with its policy, or add it to the non-tenant list; never leave it in between.

`users` and `otp_codes` are not tenant tables: they are reached only through the authentication path, before any user identity exists. `service_usage` is not one either - it holds account-wide counters of calls to external services, with no user content; its only per-user rows are the personal sub-limit counters, keyed by subject and filtered in the application, and `GET /limits` only ever returns the caller's own.

## Authentication

- **Passwordless.** A 6-digit code is emailed; there is no password to leak, reuse or reset.
- Codes are stored as **HMAC-SHA256 hashes** keyed with `JWT_SECRET`, never in plaintext, and compared with `hmac.compare_digest`.
- A code expires after `OTP_TTL_MINUTES` (10), dies after `OTP_MAX_ATTEMPTS` (5) wrong guesses, and requesting a new one marks all previous unused codes for that address as used.
- The verification row is selected `FOR UPDATE`, so parallel guesses cannot race the attempt counter.
- Rate limits: one code per address per `OTP_RESEND_COOLDOWN_SECONDS` (60), and at most `OTP_MAX_PER_IP_PER_HOUR` (20) requests per client IP.
- **Cloudflare Turnstile** guards `POST /auth/request-otp`: the browser solves a challenge, and the backend validates the token with `siteverify` before a code is issued or an email is sent. With `TURNSTILE_SECRET_KEY` empty the check is skipped entirely (local development and tests); with it set, a request without a token is rejected with `403` before any database or email work happens.
- The session is a JWT (HS256) in a cookie: `httpOnly`, `Secure`, `SameSite=Lax`, `Path=/`, lifetime `JWT_TTL_MINUTES` (7 days).
- Consent is asked for twice, and the second one is the binding one: `POST /auth/request-otp` refuses to send a code without `accepted_terms: true`, and `POST /auth/verify-otp` - the request that actually creates the account - refuses with `422` without `terms_accepted: true`. The refusal happens before the code is marked used, so a rejected registration does not burn the code. An address that already has an account signs in without the flag: it consented once, and `terms_version` records to what.
- **Changing the legal texts means bumping two values in one commit:** `UPDATED` in `landing/src/legal.js` and `CURRENT_TERMS_VERSION` in `app/config.py`. `tests/test_terms.py` fails if they drift apart; bumping them is what sends every existing account through the re-consent screen.
- **Consent is recorded.** Registering writes `users.terms_accepted_at` and `users.terms_version` from `CURRENT_TERMS_VERSION`; signing in again never overwrites them. When the stored version is missing or no longer current, `/me` answers `terms_required: true`, every data route answers `403`, and only `GET /me`, `POST /me/accept-terms`, `POST /auth/logout` and `DELETE /me` still work - deleting the account must not be held hostage to a consent screen. The version is a server constant; the client never sends it.

## CSRF and CORS

Cookie authentication means a cross-site request would otherwise carry credentials. Two measures:

- Every non-safe request must send `X-Requested-With: groundline`. A cross-origin page cannot set a custom header without a CORS preflight, and the preflight is answered against an explicit origin allowlist.
- `CORS_ORIGINS` is an explicit list with `allow_credentials=True`; it must never be `*`, and with credentials enabled browsers reject the wildcard anyway.

`SameSite=Lax` already blocks the common cross-site POST; the header requirement covers the remaining top-level-navigation cases and any client that treats `Lax` loosely.

## Response headers

Both static projects are served by Vercel, which reads its headers from `vercel.json`. Those two files are generated by `scripts/headers.mjs`, never edited by hand: run `npm run build` in `landing/`, then `node scripts/headers.mjs` from the repository root. The landing CI job regenerates them and fails on a diff, so a stale policy cannot reach production.

Every response carries `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, a `Permissions-Policy` that turns off camera, microphone, geolocation, payment and topic-based advertising, and a **Content-Security-Policy in enforce mode since 2026-09-20**.

| Directive | App (`frontend/`) | Landing (`landing/`) |
| --- | --- | --- |
| `default-src` | `'self'` | `'self'` |
| `script-src` | `'self'` + Turnstile | `'self'` |
| `style-src` | `'self' 'unsafe-inline'` + Google Fonts | same |
| `img-src` | `'self' data:` | `'self' data:` |
| `font-src` | `'self'` + Google Fonts | same |
| `connect-src` | `'self'`, the `VITE_API_URL` origin, Turnstile | `'self'` |
| `frame-src` | Turnstile | - |
| `object-src`, `base-uri`, `form-action`, `frame-ancestors` | `'none'`, `'self'`, `'self'`, `'none'` | same |

`script-src` contains neither `'unsafe-inline'` nor any hash, because **neither site has an executable inline script**. It once did: the landing used the `@vercel/analytics` and `@vercel/speed-insights` Astro components, which inline their bundle into every page, and the policy allowed them by `sha256`. That broke in production the moment the policy started enforcing - the bundle Vercel's builder emits is 279 bytes longer than the one a local build emits, so hashes computed here never matched what was served. The components are gone; both pages now load `/_vercel/insights/script.js` and `/_vercel/speed-insights/script.js` by `src` from their own origin, which `'self'` covers and no build difference can invalidate. Hash-pinning a bundle that a different machine compiles is not worth repeating.

The JSON-LD blocks Astro writes are `type="application/ld+json"`. Browsers never execute them, so `script-src` does not govern them and they need no hashes - production confirmed this by not blocking a single one.

`style-src` does need `'unsafe-inline'`: React sets inline `style` attributes on the meters and progress bars.

The `connect-src` origin is derived from `VITE_API_URL`, not written by hand, so the policy cannot drift away from the API the app actually calls.

**Rolling back is renaming one constant:** set `CSP_HEADER` in `scripts/headers.mjs` back to `Content-Security-Policy-Report-Only`, regenerate, and the same policy only reports instead of blocking.

## Uploads

- Extensions are restricted to `.pdf`, `.txt`, `.md`, and the file name to the 512 characters the column holds.
- `Idempotency-Key` is capped at 128 characters and the email address at 178 - the width left in `service_usage.quota_key` after the longest personal quota key. All three answer `422` instead of failing inside the database.
- The size limit is enforced **while reading** the stream in 1 MB pieces, so an oversized upload is rejected without being buffered in full, in memory or on disk.
- The body is spooled to a temporary file that is deleted on every path: success, failure and rejection.
- PDF parsing failures and non-UTF-8 text produce `422`, not a stack trace.
- Per-user document count and total storage quotas are checked before the file is accepted.

## Abuse limits

| Limit | Default | Where |
| --- | --- | --- |
| Queries per day (cache hits excluded) | 50 | `QUERIES_PER_DAY` |
| Language-model tokens per day (cache hits excluded) | 20 000 | `USER_TOKENS_PER_DAY` |
| Questions being answered at once, per user | 1 | fixed |
| Gap between two questions from one user | 15 s | `QUERY_MIN_INTERVAL_SECONDS` |
| Documents per user | 1 | `MAX_DOCUMENTS` |
| Storage per user | 200 MB | `MAX_STORAGE_MB` |
| Upload size | 0.3 MB | `MAX_UPLOAD_MB` |
| Concurrent `/events` streams per user | 5 | `EVENTS_MAX_SUBSCRIBERS` |
| OTP requests per IP per hour | 20 | `OTP_MAX_PER_IP_PER_HOUR` |
| Login codes per email address per day | 3 | `RESEND_PER_USER_PER_DAY` |

The per-user checks count finished questions in `query_log`, which is written at the end of the pipeline, so on their own they could be raced by firing many questions at once. A second question from the same account while one is still being answered gets `429` before any check or model call runs. The claim is held in the API process and released when the answer stream ends; a claim older than ten minutes is treated as abandoned. It is per process, which matches the single-process deployment; several API processes would need the claim in Postgres or Redis instead.

`use_cache=false` in `POST /query` and the exemption from the token budget are for accounts with the `eval` or `admin` role (`users.role`, default `user`); any other account asking to bypass the cache gets `403`. Roles are set in the database only - no endpoint changes them.

External service quotas are enforced on top of these: when a provider's free tier (or the DeepInfra budget) is spent, the affected endpoint answers `429` naming the service and its reset time, instead of failing at the provider. See [Architecture → service limits](architecture.md#service-limits).

## Untrusted text reaching the model

Three kinds of text reach a prompt, and none of them are trusted: the question, the fragments retrieved from the user's own documents, and the model's own output when it is fed back into the next prompt. `app/guard.py` is the single place that normalises them.

- **Invisible instructions are removed.** `guard.clean()` deletes zero-width, soft-hyphen, bidi-override and isolate characters and the Unicode tag block `U+E0000-E007F` - the "ASCII smuggling" range, which renders as nothing in the browser and as plain text to the model - then applies NFKC, so fullwidth and lookalike forms cannot slip a keyword past a filter. Questions are cleaned in the `QueryIn` validator, so a body that is only invisible characters answers `422` instead of reaching the pipeline. **Document text is cleaned at chunking time**, so what is embedded, searched, prompted with and shown as a source are the same string.
- **Length is re-checked after normalisation.** NFKC expands: one `U+FDFA` becomes 18 characters. The 2000-character cap is enforced again on the normalised text, not only on the bytes that arrived.
- **Prompt regions are fenced.** The question goes inside `<user_question>` and the fragments inside `<context>` as `<fragment n="1" source="...">` elements. Those five tag names are neutralised inside every piece of untrusted text (`guard.neutralize`), so neither a question nor a PDF can close the block it sits in and open a forged one. Citation numbers come from the `n=` attribute, which nothing in the data can write. The file name goes in the `source=` attribute with quotes and newlines stripped - it is attacker-controlled on upload, and was previously interpolated raw.
- **The system prompts say the fenced regions are data.** Delimiting alone is not a control; the instruction that text inside them is never to be obeyed is what the model acts on. Treat the pair as best-effort mitigation, not a boundary: an LLM has no privilege separation, which is why nothing downstream of the answer executes anything.
- **Model output fed back into a prompt is clamped.** The rewritten query and the `missing` field of the sufficiency verdict are model-generated, document-influenced strings that go straight into the next prompt. Both are cleaned, tag-neutralised and cut to 500 / 200 characters, so a document cannot make the loop grow a prompt without bound or re-inject through the retry path.
- **Uploaded file names are sanitised** to their last path segment, without control characters, before the extension check or any database write.

`tests/test_guard.py` covers each of these with the forged payload it is meant to defeat, and needs no database.

## PII and third-party telemetry

The question, the retrieved fragments and the answer *must* reach the LLM provider - that is the product, and [Data handling](#data-handling) says so plainly. Observability is different: it is optional, it is a second vendor, and it retains.

`guard.redact()` masks email addresses, card-shaped digit runs, IBANs, US SSNs, international phone numbers and the common API-key shapes (`sk-`/`pk-`, `ghp_`, `AKIA...`, JWTs). It is applied in two places:

- **Every LangFuse observation.** `app/api/main.py` creates the LangFuse client with `mask=guard.mask_telemetry`, and the SDK runs that function over the input, output and metadata of every span and generation before export, walking nested dicts and lists. That covers the traces the application writes itself (the query, the cache lookup with the nearest cached question, rerank, ingest, the Jev calls) and the generations the `langfuse.openai` wrapper records for every LLM call - the full prompt with the question and the retrieved fragments, and the answer. Every client `get_client()` returns carries the same mask; `tests/test_guard.py` checks that in a process with LangFuse keys set.
- **The `DEBUG` log line** that prints the question.

Set `TELEMETRY_REDACTION=false` to see raw text in traces while debugging; it defaults to on.

Redaction is pattern-based, so it is a reduction, not a guarantee: free-form names, addresses and account numbers in an unusual format pass through. A deployment that cannot accept that leaves the LangFuse keys empty, which disables the export entirely.

## Data handling

- `DELETE /documents/{id}` and `DELETE /documents` also clear the answer cache, so deleted content cannot be served from a cached answer.
- `DELETE /cache` and `DELETE /history` let a user drop stored questions and answers without deleting documents.
- `DELETE /me` deletes the user row; documents, chunks, cache, history and ingest jobs cascade, and pending OTP rows plus the personal `service_usage` counters keyed by that address are removed explicitly, so the address does not survive the account.
- Prompts and answers are sent to the configured LLM provider, and with `EMBEDDING_PROVIDER=api` / `RERANK_PROVIDER=api` document fragments are sent to those providers too. Set both to `local` for a deployment where document text never leaves the container.
- LangFuse traces include questions, answers and retrieved fragments, with the patterns above masked. Leave the keys empty if that data must not go to a third party at all.
- Server logs carry the user id, cache hit and similarity, but not the question text; the question and the nearest cached question are logged at `DEBUG` only.

## Known limitations

- **Sessions cannot be revoked.** JWTs are stateless: logout clears the cookie, but a token already copied elsewhere stays valid until it expires (or until the account is deleted). A token version column on `users`, checked per request, would fix this.
- **Consent before the version existed is unrecorded.** Accounts created before migration `0006` carry `NULL`, which is treated as "has not accepted" - they meet the re-consent screen on their next visit and are recorded from there.
- **`X-Forwarded-For` is trusted from any proxy** (`--forwarded-allow-ips '*'`). Expose the backend only behind a reverse proxy you control (Render, nginx), or the per-IP OTP limit can be bypassed with a forged header.
- **Rate limits are shared only when Upstash is configured.** With `UPSTASH_REDIS_REST_URL` and `UPSTASH_REDIS_REST_TOKEN` set, the per-IP OTP limit is counted in Redis and holds across instances; without them it falls back to a Postgres count (shared, but only over rows that exist). A Redis outage fails open to the local counters rather than rejecting logins. The `/events` subscription limit is deliberately per-process: it counts the queues a process is actually serving, so a restart cannot strand a slot that no stream holds.
- **No antivirus or content scanning** on uploads. Files are parsed as text and never executed, but nothing inspects them for malicious payloads.
- **`DEV_MODE=true` prints login codes to the log.** It exists for local development; enabling it in production hands out sessions to anyone who can read logs.
