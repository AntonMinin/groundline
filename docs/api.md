# API

Base URL: `http://localhost:8000` locally, `https://api.<your-domain>` in production. Interactive docs at `/docs`.

Two rules apply to every request from a browser:

- **Credentials.** Authentication is a cookie (`groundline_session`, httpOnly). Send requests with `credentials: 'include'` / `curl -b cookies.txt`.
- **`X-Requested-With: groundline`.** Required on every request the frontend makes. It is the CSRF defence: a cross-origin page cannot set a custom header without passing the CORS preflight, and the allowlist rejects it. See [Security](security.md).

## Endpoints

| Method | Path | Description |
| --- | --- | --- |
| POST | `/auth/request-otp` | `{email}` → 202, sends a 6-digit code (429 on cooldown or IP limit) |
| POST | `/auth/verify-otp` | `{email, code}` → sets the session cookie (401 on an invalid or expired code) |
| POST | `/auth/logout` | clears the session cookie |
| GET | `/me` | the current user |
| DELETE | `/me` | deletes the account with all documents, cache and history |
| POST | `/ingest` | multipart `file` (pdf/txt/md) → 202 with a job id; processing runs in the background |
| GET | `/jobs/{id}` | ingest job status (`queued`, `processing`, `done`, `error`) |
| GET | `/documents` | the user's documents |
| DELETE | `/documents/{id}` | deletes one document (also clears the answer cache) |
| DELETE | `/documents` | deletes all documents of the user (also clears the answer cache) |
| DELETE | `/cache` | clears the semantic answer cache, documents untouched |
| DELETE | `/history` | clears the query history |
| GET | `/history` | recent questions and answers, with per-step metrics |
| GET | `/stats` | cache hit rate, tokens saved, usage and limits |
| GET | `/events` | SSE channel with live pipeline and ingest events for the current user |
| POST | `/query` | `{question, use_cache?}` → `text/event-stream` |
| GET | `/health` | liveness, no database access |

### POST /ingest

Multipart upload. Returns `202` with a job; indexing happens in the background and progress arrives on `/events`.

- `415` unsupported extension, `422` empty or unreadable file, `413` larger than `MAX_UPLOAD_MB`, `429` document or storage quota reached.
- An `Idempotency-Key` header replays an existing job with `200` instead of processing the same file twice.

```json
{ "id": "…", "filename": "handbook.md", "status": "queued", "error": null, "document_id": null, "created_at": "…" }
```

### POST /query

```json
{ "question": "How many days per week can I work from home?", "use_cache": true }
```

`use_cache: false` skips the cache *lookup* (the result is still recorded); the evaluation harness uses it so it measures the pipeline rather than the cache.

Responds with `text/event-stream`:

```
event: token
data: {"type": "token", "text": "Remote work is allowed "}

event: done
data: {"type": "done", "cache_hit": false, "cache_similarity": 0.9126, "cache_threshold": 0.95,
       "tokens_used": 807, "tokens_saved": 0,
       "sources": [{"filename": "handbook.md", "chunk_index": 0, "page": null, "document_id": "…",
                    "content": "…", "score": 0.97}]}

event: error
data: {"type": "error", "status": 504, "detail": "Model provider timed out"}
```

On a cache hit the whole stored answer arrives as a single `token` event, followed by `done` with `cache_hit: true` and `tokens_saved` set to what that answer originally cost.

Errors raised *before* the first token (no documents, daily quota, a provider failure during rewrite or sufficiency) are returned as ordinary HTTP status codes: `409` empty knowledge base, `429` daily limit, `502` provider unavailable, `504` provider timeout. Errors *during* generation arrive as an `error` event, because the response has already started with `200`.

### GET /events

A second SSE stream, one per user, carrying what the system is doing right now. Every pipeline node publishes on entry and exit, and background ingest jobs publish every status change.

```
event: connected
data: {"type": "connected", "timestamp": "…"}

event: node_started
data: {"type": "node_started", "node": "retrieve", "timestamp": "2026-09-16T05:12:03.114Z"}

event: node_finished
data: {"type": "node_finished", "node": "generate_answer", "cache_hit": false, "tokens": 807,
       "tokens_saved": 0, "duration_ms": 1866, "similarity": null,
       "timestamp": "2026-09-16T05:12:04.980Z"}

event: ingest
data: {"type": "ingest", "job_id": "…", "filename": "handbook.md", "status": "done",
       "error": null, "document_id": "…", "timestamp": "2026-09-16T05:11:40.002Z"}
```

Node names, in pipeline order: `check_cache`, `rewrite_query`, `retrieve`, `rerank`, `check_sufficiency`, `generate_answer`, `record`.

- A comment heartbeat (`: ping`) is sent every `EVENTS_HEARTBEAT_SECONDS` so proxies keep the connection open.
- A user may hold at most `EVENTS_MAX_SUBSCRIBERS` streams; beyond that `/events` returns `429`.
- Each subscriber has a bounded queue; events are dropped for a subscriber that falls behind rather than blocking the pipeline.

### GET /history

```json
[{ "id": "…", "question": "…", "answer": "…", "sources": [...], "cache_hit": false,
   "tokens_used": 807, "tokens_saved": 0,
   "node_metrics": [{"node": "check_cache", "cache_hit": false, "tokens": 0, "tokens_saved": 0,
                     "similarity": 0.9126, "duration_ms": 212}, "…"],
   "created_at": "…" }]
```

`node_metrics` is what lets the UI restore the chart and the pipeline diagram after a reload, without polling anything. `limit` defaults to 50, capped at 200.

### GET /stats

```json
{
  "total_queries": 3,
  "cache_hits": 1,
  "cache_hit_rate": 0.3333,
  "tokens_saved": 807,
  "tokens_used": 1646,
  "usage": {"documents": 1, "storage_bytes": 1336, "queries_last_24h": 2},
  "limits": {"queries_per_day": 50, "max_documents": 100, "max_storage_mb": 200}
}
```

`queries_last_24h` counts only queries that were *not* cache hits — a cached answer costs nothing, so it does not consume the daily quota.

## Status codes

| Code | When |
| --- | --- |
| `401` | missing, invalid or expired session; wrong or expired OTP |
| `404` | job or document not found (including one belonging to another user) |
| `409` | `/query` with no documents indexed yet |
| `413` | upload larger than `MAX_UPLOAD_MB` |
| `415` | upload is not `.pdf`, `.txt` or `.md` |
| `422` | empty file, unparsable PDF, non-UTF-8 text file, or request body validation failure |
| `429` | OTP cooldown or per-IP hourly limit; document, storage or daily query quota; too many `/events` streams |
| `502` / `504` | the model provider failed or timed out |
| `503` | the database is unavailable |

## A session with curl

```bash
H='X-Requested-With: groundline'
curl -X POST localhost:8000/auth/request-otp -H "$H" -H 'Content-Type: application/json' -d '{"email":"me@example.com"}'
# with DEV_MODE=true and no RESEND_API_KEY the code is printed in the backend log
curl -c cookies.txt -X POST localhost:8000/auth/verify-otp -H "$H" -H 'Content-Type: application/json' \
     -d '{"email":"me@example.com","code":"123456"}'
curl -b cookies.txt -X POST localhost:8000/ingest -H "$H" -H 'Idempotency-Key: handbook-1' -F file=@app/eval/data/handbook.md
curl -N -b cookies.txt localhost:8000/events -H "$H" &   # watch the pipeline live
curl -N -b cookies.txt -X POST localhost:8000/query -H "$H" -H 'Content-Type: application/json' \
     -d '{"question":"How many days per week can I work from home?"}'
curl -b cookies.txt localhost:8000/stats -H "$H"
```
