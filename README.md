# Groundline

Groundline answers questions about **your own documents**. Upload PDF, TXT or Markdown files, ask in plain language, and get an answer that quotes the exact fragments it came from — never the model's imagination.

On top of the usual RAG pipeline it keeps a **semantic answer cache**: ask the same thing in different words and the answer comes back instantly, without a single call to the language model.

**Live demo: [groundline.antonmb.com](https://groundline.antonmb.com)** — log in with a code sent to your email, upload a file, ask a question.
The API runs on a free Render instance that sleeps when idle, so the first request after a pause can take 30–50 seconds. Everything after that is fast.

## What you get

- **Answers with sources.** Every answer lists the file, fragment and page it was built from.
- **Hybrid search.** Meaning-based (vector) search and word-based (full-text) search run together, so both paraphrases and exact terms are found.
- **A second opinion on the results.** A reranker model re-reads the candidates and keeps the five that actually answer the question.
- **A self-check loop.** Before answering, the model judges whether the fragments are enough; if not, the question is reformulated and searched again (up to two extra attempts).
- **A semantic cache.** Repeat questions cost nothing and return immediately.
- **A live view of the machine.** The UI shows the pipeline stepping through its seven stages with per-step time and token cost, the share of questions the cache answered, and a bar along the bottom with how much of every external free tier is left.
- **English and Russian**, switched from the header.
- **Your documents stay yours.** Every row is tied to a user and isolated by Postgres Row-Level Security, not just by application-level filters.

## Using it

1. **Log in.** Enter your email, receive a 6-digit code, enter it. No password.
2. **Upload.** *Documents* tab → pick a `.pdf`, `.txt` or `.md` file. Indexing runs in the background; the status updates itself.
3. **Ask.** *Chat* tab → type a question. The answer streams in word by word, with sources underneath.
4. **Ask again, differently.** A paraphrase of an earlier question is served from the cache — marked *cache hit*, with the tokens it saved.
5. **Watch the counters.** The bar at the top shows the cache hit rate, tokens saved and how much of your quota is used.

## Run it locally

Requirements: Docker, and for the host-side setup Python 3.11+ and Node 24.

```bash
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # paste into JWT_SECRET
# set GROQ_API_KEY; with DEV_MODE=true and no RESEND_API_KEY the login code is printed to the backend log
docker compose up --build
```

UI on http://localhost:5173, API docs on http://localhost:8000/docs. The first start downloads the embedding and reranker models (~4.5 GB) into a Docker volume; with `EMBEDDING_PROVIDER=api` and `RERANK_PROVIDER=api` nothing is downloaded and both models are called over HTTP instead.

Running the backend and frontend on the host, tests and evaluation: see [Development](docs/development.md).

## Documentation

| Document | What is inside |
| --- | --- |
| [How it works](docs/how-it-works.md) | Plain-language walkthrough: what each block does, and how a question, an upload and a cache hit actually travel through the system. **Start here.** |
| [Architecture](docs/architecture.md) | Modules, data model, the LangGraph pipeline, the live event channel, concurrency and scaling limits. |
| [API](docs/api.md) | Every endpoint, the two SSE streams and their events, error codes, a curl session. |
| [Configuration](docs/configuration.md) | Every environment variable, its default and what it changes. |
| [Security](docs/security.md) | Tenant isolation, authentication, cookies, CSRF, rate limits, and the known limitations. |
| [Deployment](docs/deployment.md) | Production layout on Supabase + Render + Vercel + Resend, step by step. |
| [Development](docs/development.md) | Local setup, tests, ragas evaluation, tuning the cache threshold, CI. |
| [Landing](landing/README.md) | The public Astro page in front of the app: domains, deployment, screenshots, structured data. |

## Stack

FastAPI · LangGraph · Postgres 17 + pgvector · SQLAlchemy async + Alembic · Groq (`openai/gpt-oss-120b`) · BAAI `bge-m3` embeddings · BAAI `bge-reranker-v2-m3` · LangFuse · ragas · React + Vite.
