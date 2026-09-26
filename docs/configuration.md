# Configuration

Everything is read from the environment (or a `.env` file) by `app/config.py`. Start from [`.env.example`](../.env.example). Only `JWT_SECRET` has no usable default - the application refuses to start without one of at least 32 characters.

## Core

| Variable | Default | Purpose |
| --- | --- | --- |
| `JWT_SECRET` | - (required, ≥ 32 chars) | signs session tokens and HMACs OTP codes. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Changing it invalidates every session and every pending login code |
| `DEV_MODE` | `false` | when `true` and `RESEND_API_KEY` is empty, login codes are written to the log instead of emailed. Never enable in production |
| `DATABASE_URL` | local app role | runtime connection. Must be a role **without** `BYPASSRLS`, otherwise tenant isolation falls back to application filters alone |
| `MIGRATION_DATABASE_URL` | - | owner connection used by Alembic. Set only where migrations run - the CI `migrate` job, the compose `migrate` service, a developer shell - never on the web service. The service checks the schema version at start-up and refuses to start when the database is behind the code |

## Language model

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_API_KEY` | - | API key for the LLM |
| `LLM_MODEL` | `openai/gpt-oss-120b` | any model of the configured provider. Groq moved `llama-3.3-70b-versatile` to Enterprise-only, so a free-tier key gets a 404 for it |
| `LLM_BASE_URL` | `https://api.groq.com/openai/v1` | any OpenAI-compatible endpoint works |
| `LLM_TIMEOUT` | `30` | seconds; also the timeout for the rerank API |

## Embeddings and rerank

| Variable | Default | Purpose |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local` | `local` (sentence-transformers in-process) or `api` (OpenAI-compatible embeddings endpoint) |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | must match `EMBEDDING_DIM` |
| `EMBEDDING_MODEL_REVISION` | a commit of `BAAI/bge-m3` | Hugging Face revision the local model is loaded at, so a changed upstream repository cannot swap the weights. Empty loads the latest |
| `EMBEDDING_DIM` | `1024` | vector column width. Changing it requires a migration and re-indexing every document |
| `EMBEDDING_BATCH_SIZE` | `16` | texts per call; also the granularity at which ingestion releases the local inference lock |
| `EMBEDDING_API_BASE_URL` | DeepInfra | hosted bge-m3 endpoint |
| `EMBEDDING_API_KEY` | - | key for the above |
| `RERANK_PROVIDER` | `local` | `local` (CrossEncoder in-process) or `api` (Pinecone Inference) |
| `RERANKER_MODEL` | `BAAI/bge-reranker-v2-m3` | local reranker weights |
| `RERANKER_MODEL_REVISION` | a commit of `BAAI/bge-reranker-v2-m3` | Hugging Face revision of the local reranker, pinned the same way |
| `RERANK_API_URL` | `https://api.pinecone.io/rerank` | hosted reranker |
| `RERANK_API_MODEL` | `bge-reranker-v2-m3` | hosted model name |
| `RERANK_API_KEY` | - | key for the above |
| `PRELOAD_MODELS` | `true` | load local models at start-up instead of on the first request. Set `false` when both providers are `api` |
| `TORCH_NUM_THREADS` | `0` (torch default) | caps intra-op threads for the local models. Set it below the core count when the same instance also serves requests |

Local and hosted bge-m3 produce the same vectors (identical weights), so switching `EMBEDDING_PROVIDER` does **not** require re-indexing.

## Pipeline

| Variable | Default | Purpose |
| --- | --- | --- |
| `CHUNK_SIZE` | `700` | tokens per chunk |
| `CHUNK_OVERLAP` | `100` | tokens shared between neighbouring chunks |
| `RETRIEVAL_CANDIDATES` | `20` | rows fetched by each search and kept after fusion |
| `RERANK_TOP_K` | `5` | fragments handed to the LLM |
| `MAX_REWRITES` | `2` | extra search attempts when the sufficiency check says no |
| `CACHE_SIMILARITY_THRESHOLD` | `0.90` | cosine similarity at which a stored answer is reused. See [tuning](development.md#tuning-the-cache-threshold) |

Changing `CHUNK_SIZE` or `CHUNK_OVERLAP` only affects documents indexed afterwards; existing chunks are not re-cut.

## Jev decisions

[Jev](https://docs.typesafe.ai/concepts/system-one) is a System One model: it returns calibrated probabilities for typed questions and generates no text. Groundline uses it for three decisions (see [How it works → Jev](how-it-works.md#jev-three-fast-decisions)). Every call is fail-open: an error, a timeout or a spent budget means the pipeline behaves exactly as it does without Jev.

| Variable | Default | Purpose |
| --- | --- | --- |
| `JEV_ENABLED` | `false` | main switch. `false` builds the original seven-step graph, so behaviour is identical to a build without Jev. `true` with no key for the chosen provider also keeps Jev off, with a warning in the log |
| `JEV_PROVIDER` | `openrouter` | `openrouter` (`POST https://openrouter.ai/api/v1/systemone`, billed to OpenRouter credits) or `typesafe` (`POST https://api.typesafe.ai/v1/systemone`). Same request and response shape. `typesafe` without `TYPESAFE_API_KEY` logs a warning and uses `openrouter` |
| `OPENROUTER_API_KEY` | - | key for the OpenRouter System One API. Backend only |
| `TYPESAFE_API_KEY` | - | key for the TypeSafe API. Backend only |
| `JEV_MODEL` | `jev-1.13` | pinned version, so the thresholds below stay valid when `jev-latest` moves. OpenRouter maps it to `typesafe/jev-1.13` |
| `JEV_TIMEOUT_CRITICAL_MS` | `1500` | timeout for the two decisions on the path to the answer: the cache check and `jev_sufficiency`. About twice the measured p95 (702 ms, see [Evaluation](evaluation.md)). No retries: a slow Jev falls back instead of delaying the answer |
| `JEV_TIMEOUT_MS` | `2000` | timeout for `check_grounding`, which runs after `done` and only delays the badge and the cache write. Measured p95 681 ms |
| `JEV_PRICE_PER_1M` | `0.042` | USD per 1M input tokens, used to price TypeSafe calls. OpenRouter reports the exact `usage.cost` itself |
| `JEV_MONTHLY_BUDGET_USD` | `1.0` | monthly cap on Jev spend. Unlike DeepInfra, reaching it skips Jev and keeps answering questions |
| `JEV_SUFFICIENT_THRESHOLD` | `0.85` | Jev's probability that the fragments are enough, at or above which the LLM sufficiency check is skipped. Below it the LLM check runs as before and still writes the `missing` hint for the rewrite |
| `JEV_CACHE_VERIFY_FROM` | `0.85` | lower end of the range Jev checks. A nearest question between this value and `CACHE_SIMILARITY_THRESHOLD` becomes a hit when Jev says it asks the same thing; if Jev fails it stays a miss, as without Jev |
| `JEV_CACHE_VERIFY_BELOW` | `0.97` | upper end of the range. A hit from `CACHE_SIMILARITY_THRESHOLD` up to this value is confirmed by Jev before the stored answer is returned; if Jev fails it stays a hit. At or above it the similarity alone decides |
| `JEV_SAME_QUESTION_THRESHOLD` | `0.5` | Jev's probability that the new and the stored question ask for the same thing, below which a would-be hit becomes a miss |
| `JEV_GROUNDED_THRESHOLD` | `0.9` | probability of the `supported` verdict at or above which an answer is written to the cache. A Jev failure falls back to the original rule |

## Quotas and ingestion

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAX_UPLOAD_MB` | `0.3` | per-file limit in megabytes, enforced while the upload is being read. Fractions are allowed, so `0.3` caps a file at about 300 KB |
| `MAX_DOCUMENT_CHARS` | `1000000` | characters of extracted text per document. A small compressed PDF can expand to tens of megabytes of text; extraction stops and the upload fails with `422` once the text passes this size, before any chunk is embedded |
| `MAX_PDF_PAGES` | `500` | pages per PDF, checked before any text is extracted |
| `QUERIES_PER_DAY` | `50` | per user, rolling 24 hours; cache hits are not counted |
| `USER_TOKENS_PER_DAY` | `20000` | language-model tokens per user, rolling 24 hours, summed from `query_log.tokens_used`. Keeps one account from spending the shared Groq daily quota for everyone. `0` disables it. Accounts with the `eval` or `admin` role are exempt |
| `QUERY_MIN_INTERVAL_SECONDS` | `15` | shortest gap between two questions from one user. `0` disables it |
| `MAX_DOCUMENTS` | `1` | per user. At the limit `/ingest` answers `429` and the document has to be deleted first |
| `MAX_STORAGE_MB` | `200` | total uploaded bytes per user |
| `INGEST_WORKERS` | `1` | background indexing concurrency. Keep it low on small instances - embedding a large PDF is the memory peak |
| `INGEST_QUEUE_SIZE` | `100` | queued jobs before `/ingest` blocks |
| `RESEND_PER_USER_PER_DAY` | `3` | personal sub-limit: login codes one email address may request per day, under the service-wide Resend quota. `0` disables it |

## External service limits

The free-tier ceilings themselves live in the registry in `app/limits.py` (limit, period, data source, pricing URL) rather than in the environment, so that changing one is a reviewed edit. Only the paid service is configured here:

| Variable | Default | Purpose |
| --- | --- | --- |
| `DEEPINFRA_PRICE_PER_1M` | `0.01` | USD per 1M embedding tokens, used to price local spend when the balance endpoint is unavailable |
| `DEEPINFRA_MONTHLY_BUDGET_USD` | `5.0` | monthly spending cap. Reaching it blocks uploads and queries with 429, exactly like an exhausted free tier |
| `LIMITS_AUTOCHECK_ENABLED` | `true` | the daily job that re-reads each provider's pricing page and compares the published number with the registry. Never changes a limit by itself. Also skipped when `GROQ_API_KEY` is empty |
| `LIMITS_CHECK_MODEL` | `openai/gpt-oss-20b` | model used to read a limit out of a pricing page. Groq counts rate limits **per model**, so a model different from `LLM_MODEL` gives the job its own token-per-minute budget instead of competing with people's questions |
| `LIMITS_CHECK_SPACING_SECONDS` | `60` | pause between pricing pages. The whole set as one burst is around 30K tokens, well over a 8K-per-minute window; one page a minute stays inside it |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | - | alert delivery. Empty means alerts stay in the log and in `/limits` |

See [Architecture → service limits](architecture.md#service-limits) for what is metered where.

## Authentication and cookies

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTP_HMAC_SECRET` | - (falls back to `JWT_SECRET`) | key for the HMAC of stored login codes. Setting it lets `JWT_SECRET` be rotated without touching pending codes, and the other way round. At least 32 characters when set |
| `JWT_TTL_MINUTES` | `10080` (7 days) | session lifetime. Tokens are stateless and cannot be revoked before expiry |
| `OTP_TTL_MINUTES` | `10` | login code lifetime |
| `OTP_MAX_ATTEMPTS` | `5` | wrong guesses before a code is dead |
| `OTP_RESEND_COOLDOWN_SECONDS` | `60` | minimum gap between codes for one address |
| `OTP_MAX_PER_IP_PER_HOUR` | `20` | code requests per client IP |
| `COOKIE_NAME` | `groundline_session` | session cookie name |
| `COOKIE_DOMAIN` | - | e.g. `.example.com` so `app.` and `api.` share the session. Leave empty for localhost |
| `COOKIE_SECURE` | `true` | set `false` only for plain-HTTP local development |
| `CORS_ORIGINS` | `http://localhost:5173` | comma-separated list of allowed frontend origins. Credentials are allowed, so this must never be `*` |
| `RESEND_API_KEY` | - | email delivery; without it and without `DEV_MODE`, login fails with 502 |
| `RESEND_FROM` | `Groundline <onboarding@resend.dev>` | must use a domain verified in Resend |
| `TURNSTILE_SITE_KEY` | - | Cloudflare Turnstile widget key, served to the frontend by `GET /config`. Empty means no widget is rendered |
| `TURNSTILE_SECRET_KEY` | - | server-side key for `siteverify`. **Empty disables the captcha check entirely** - that is the local-development and test default |

## Shared rate limiting

| Variable | Default | Purpose |
| --- | --- | --- |
| `UPSTASH_REDIS_REST_URL` | - | Upstash Redis REST endpoint. With both variables set, the per-IP OTP limit is counted in Redis and therefore shared across instances |
| `UPSTASH_REDIS_REST_TOKEN` | - | REST token for the above. Empty (either one) falls back to the per-process and Postgres counters |

Upstash is failure-tolerant by design: if the REST call errors or times out, the request falls back to the local limit rather than failing. Free-tier budget matters here - each OTP request costs 2 commands out of 500K per month.

## Live events

| Variable | Default | Purpose |
| --- | --- | --- |
| `EVENTS_HEARTBEAT_SECONDS` | `15` | comment ping interval that keeps proxies from closing `/events` |
| `EVENTS_QUEUE_SIZE` | `200` | buffered events per subscriber; a subscriber that overflows loses events instead of blocking the pipeline |
| `EVENTS_MAX_SUBSCRIBERS` | `5` | concurrent `/events` streams per user |

## Observability

| Variable | Default | Purpose |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | - | tracing credentials; tracing is disabled when either is empty |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | must match the region the keys were issued in: `cloud.langfuse.com` for EU, `us.cloud.langfuse.com` for US. A US key pair against the EU host authenticates fine nowhere and fails every span export with `401`. Self-hosted LangFuse works too |

The LangFuse SDK reads these from the process environment, which a `.env` file does not populate on its own - so `app/config.py` exports them at import time, without overwriting variables that are already set. That is what makes tracing work when the backend runs from the host with only a `.env`, the same as it already did in Docker and on Render.

## Used outside the application

| Variable | Where | Purpose |
| --- | --- | --- |
| `POSTGRES_PASSWORD` / `APP_DB_PASSWORD` | `docker-compose.yml` | passwords for the owner and application roles created by `docker/postgres-init.sh` |
| `DB_PORT` | `docker-compose.yml` | host port for Postgres, `5433` by default so it does not clash with a local server |
| `INSTALL_LOCAL_MODELS` | `Dockerfile` build arg | `false` skips torch and the local model dependencies. Render builds with `false` |
| `HF_HOME` | container | where model weights are cached (a Docker volume in compose) |
| `PORT` | container | port uvicorn binds to; Render sets it |
| `VITE_API_URL` | frontend build | API base URL. Empty means `/api`, which the nginx image proxies to the backend |
