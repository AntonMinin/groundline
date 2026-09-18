# Development

- [Setup](#setup)
- [Running backend and frontend on the host](#running-backend-and-frontend-on-the-host)
- [Migrations](#migrations)
- [Tests](#tests)
- [Evaluation with ragas](#evaluation-with-ragas)
- [Tuning the cache threshold](#tuning-the-cache-threshold)
- [Reading the logs](#reading-the-logs)
- [CI](#ci)

## Setup

Requirements: Docker, Python 3.11+, Node 24.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET
# set GROQ_API_KEY; with DEV_MODE=true and no RESEND_API_KEY the login code is printed to the backend log
```

Everything in Docker:

```bash
docker compose up --build
```

UI on http://localhost:5173 (nginx proxies `/api` to the backend), API docs on http://localhost:8000/docs. The first start downloads bge-m3 and bge-reranker-v2-m3 (~4.5 GB) into the `models` volume; set `EMBEDDING_PROVIDER=api` and `RERANK_PROVIDER=api` to skip that entirely.

## Running backend and frontend on the host

```bash
docker compose up -d db
python -m venv .venv && .venv/Scripts/activate        # source .venv/bin/activate on Linux/macOS
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements-dev.txt -r requirements-local.txt
alembic upgrade head
uvicorn app.api.main:app --reload

cd frontend && npm install && npm run dev
```

The database container listens on port **5433** so it does not clash with a local Postgres. `docker/postgres-init.sh` creates both roles: the owner (`groundline`) and the restricted application role (`groundline_app`, `NOBYPASSRLS`) that the app connects as.

Skip the torch install if you set both providers to `api`; `requirements.txt` alone is then enough.

## Migrations

```bash
alembic revision --autogenerate -m "what changed"
alembic upgrade head
```

Alembic connects with `MIGRATION_DATABASE_URL` (the owner role), not `DATABASE_URL` — the application role cannot create tables. A new tenant table needs three things added by hand in the migration: the grant to `groundline_app`, `ENABLE`/`FORCE ROW LEVEL SECURITY`, and the `tenant_isolation` policy. Copy the block from `0001_initial.py`.

A table that is **not** tenant-scoped needs the opposite treatment: a grant plus an explicit `DISABLE ROW LEVEL SECURITY`, as in `0005_non_tenant_tables_rls.py`. Hosted Postgres can turn RLS on for new tables by itself, and RLS without a policy means the application reads nothing. `tests/test_isolation.py` fails on any table caught in between.

## Tests

```bash
docker compose up -d db
pytest -q
```

Tests run against the `groundline_test` database **as the restricted application role**, so the isolation tests exercise the real RLS policies rather than a mock of them. The LLM, embeddings and search are mocked in the graph tests, so the suite needs no API keys.

| File | Covers |
| --- | --- |
| `test_chunking.py` | token-based splitting, overlap, page numbers |
| `test_fusion.py` | reciprocal rank fusion ordering |
| `test_graph.py` | pipeline routing: cache hit, retry loop, retry exhaustion, cache write conditions |
| `test_auth.py` | OTP issue/verify, expiry, attempt limits, cooldown, CSRF header |
| `test_isolation.py` | tenant isolation under RLS with unfiltered queries |
| `test_ingest.py` | upload validation, quotas, idempotency, background job lifecycle |
| `test_events.py` | subscriber limits, event fan-out, slow-consumer drops, heartbeats |
| `test_inference.py` | serialisation of local model calls, lock release on failure |
| `test_account.py` | account deletion cascade, cache and history clearing, quotas, CSRF header, database outage → 503 |
| `test_ratelimit.py` | shared rate limits over Upstash, fallback when it is absent or failing |
| `test_limits.py` | usage counters, 429 at the ceiling, provider headers over local counters, personal sub-limits |
| `test_limits_check.py` | the daily pricing-page check, its flag, Telegram alerts and their dedup |
| `test_eval_upload.py` | the evaluation script's upload path: waiting for indexing, failing on a broken job, giving up on a stuck one |

The frontend has its own check, run by Node with no test framework:

```bash
cd frontend && npm test          # node --test src/*.test.js
```

It covers `telemetry.js` — the limit thresholds behind the colours in the limits bar (green above 50% remaining, yellow 20–50%, red below 20%), which quota the collapsed bar reports, and duration formatting.

## Evaluation with ragas

The evaluation runs against a live API in a **separate** virtualenv — ragas pins LangChain versions that conflict with the application's.

```bash
python -m venv .venv-eval && .venv-eval/Scripts/activate
pip install -r requirements-eval.txt
export GROQ_API_KEY=...
export GROUNDLINE_SESSION=...   # the groundline_session cookie value after logging in
python app/eval/run_eval.py app/eval/data/dataset.json --docs app/eval/data/handbook.md
```

The dataset is a JSON list of `{question, reference}`. The script uploads the documents and **waits for indexing to finish** — `/ingest` only queues the work, so it polls `/jobs/{id}` until the job reports `done` and fails loudly if it reports `error`. Then it sends every question with `use_cache=false` (so it measures the pipeline, not the cache), and reports faithfulness, context precision, context recall and answer correctness per question and on average, writing `eval_results.json`.

What the metrics mean in practice: **faithfulness** drops when the answer states something the retrieved fragments do not support (hallucination), **context recall** drops when retrieval missed the fragment that held the answer, and **context precision** drops when the top-5 is padded with irrelevant chunks — that is, low recall points at search, low precision at the reranker, low faithfulness at the prompt.

## Tuning the cache threshold

`CACHE_SIMILARITY_THRESHOLD` decides when two differently worded questions count as the same one. Too high and paraphrases miss; too low and a different question gets someone else's answer. It is chosen from measurements, not guessed: **every query logs the similarity to the nearest cached question, whether or not it cleared the threshold.**

```
INFO app.graph.pipeline cache lookup user=… hit=False similarity=0.9126 threshold=0.9500
     question='How many days can I work remotely?' nearest='How many days per week can I work from home?'
```

The same numbers reach the `done` event of `/query` (`cache_similarity`, `cache_threshold`), the `check_cache` node event on `/events`, and the LangFuse span metadata.

To collect a batch at once:

```bash
python app/eval/cache_probe.py questions.txt        # one question per line, or a JSON list
```

It prints HIT/MISS with the similarity for each question, plus the observed ranges. Those ranges bracket the answer: set the threshold **above** the highest similarity that produced a wrong hit and **below** the lowest that produced a miss you wanted to hit. If the two ranges overlap, no threshold separates them and the fix is elsewhere (different questions really do read alike) — keep the higher value, since a wrong hit is worse than a wasted LLM call.

## Reading the logs

```
INFO app.graph.pipeline cache lookup user=… hit=False similarity=0.9126 threshold=0.9500
     ingest_pending=1 inference_waiting=1 question=… nearest=…
```

- `ingest_pending` — queued plus running ingest jobs.
- `inference_waiting` — callers holding or waiting for the local inference lock.

Together they explain a slow answer after the fact: with local models, a query that coincides with an indexing job waits for the lock. A call that waits more than a second logs its own line, and the wait is attached to the LangFuse span as `lock_wait_ms`. See [Architecture → local model inference](architecture.md#local-model-inference-and-cpu-contention).

## CI

`.github/workflows/ci.yml` runs on every push and pull request: backend tests against a pgvector service container with the restricted role created up front, and a frontend `npm ci && npm run build`. A manual `workflow_dispatch` with `migrate = true` applies Alembic migrations to the production database using the `production` environment's `MIGRATION_DATABASE_URL` secret.
