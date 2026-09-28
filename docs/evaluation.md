# Evaluation

Two sources of numbers, both shown on the landing page:

- **Live metrics** from the questions people actually ask, at `GET /metrics/live`.
- **ragas runs** on a fixed corpus and question set, at `GET /eval/status`.

## Live metrics

Every answered question writes one anonymous row to `query_metrics`: whether Jev was on, cache hit, LLM tokens, and the per-node timings and Jev traces. It holds no user id and no text, and it is deleted together with its `query_log` row when a user clears their history or deletes the account. `GET /metrics/live` is public and returns, for the last 1000 questions with and without Jev:

| Field | Meaning |
| --- | --- |
| `answer_ms` | sum of the node durations up to `done`, cache misses only |
| `llm_calls` | `rewrite_query`, `check_sufficiency` and `generate_answer` runs |
| `llm_tokens` | LLM tokens as reported by the provider |
| `cache_hit` | share of questions answered from the cache |
| `jev_ms` | time spent waiting for Jev on the question |
| `supported` | share of graded answers whose verdict was `supported` |
| `jev_cost_usd` | this month's Jev spend divided by this month's Jev questions |
| `node_ms` | average time per node, per question |

Each mode has an `average` and the `last` question. `server` adds one database session, one database round trip and a fixed CPU loop, measured on the request, so a slow node can be told apart from a slow link or a starved CPU.

### What the first production numbers showed

Before any latency work, with Jev v1 on the free Render instance: 42 s to the full answer without Jev and 57 s with it, on cache misses. The CPU loop ran in 10 ms, as on a laptop; one empty database session took about 1.1 s and one round trip 178 ms, so the Render instance and the Supabase database are far apart. A question opened about twenty sessions (usage counters, cache lookup, search, log) and each Jev, Pinecone and Upstash call set up a new TLS connection. The changes since:

- usage counters are read once per question and written once at its end, in one transaction;
- the independent database work runs concurrently: the pre-question checks, the counter read, and with Jev the search for the question as asked next to the cache lookup;
- `done` is sent before the query log is written;
- one pooled keep-alive HTTP client serves Jev, Pinecone and Upstash;
- a GitHub Actions ping every ten minutes keeps the free instance from sleeping.

The largest remaining cost is the distance to the database. Putting the Render service in the same region as the Supabase project removes most of it.

## ragas on the GitLab Handbook

### Corpus

Eight pages of the [GitLab Handbook](https://gitlab.com/gitlab-com/content-sites/handbook) on time off, leave, benefits, expenses and travel, pinned to commit `f243917f`: 70 chunks. The texts are not in this repository; `app/eval/corpus/fetch_gitlab.py` downloads them and checks each against the SHA-256 in `app/eval/corpus/manifest.json`. The GitLab Handbook is © GitLab Inc. and licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).

### Dataset

`app/eval/data/gitlab_dataset.json`: 29 questions (12 answered by one chunk, 7 across documents, 5 unanswerable, 5 distractors; 5 in Russian) and 30 cache pairs (paraphrases and look-alikes). `app/eval/data/dataset.json` is a smaller smoke set over one handbook.

### Method

Same questions in the same order, cache cleared, `use_cache=false`. The judge is ragas with `openai/gpt-oss-20b`, `max_tokens=4096`. Without Jev and Jev v1 were judged through OpenRouter on one pinned upstream (Parasail) and are kept as they were; from Jev-first on, the judge runs on the free Groq tier like the pipeline, and OpenRouter serves only Jev. The unfinished extras of the two earlier runs (the Jev v1 repeat judgements and the cache pairs) were not completed, so no run mixes two judges. The runs execute in GitHub Actions (`.github/workflows/eval.yml`, started by hand) against a throwaway database with the local models, so their latencies say nothing about production; the live metrics do. Progress is stored in `eval_runs` and resumes after a quota stop.

### Results

The table is filled in by the evaluation workflow from the stored runs; the Jev-first column updates itself when that run has answered all questions.

<!-- results:start -->
| | Without Jev | Jev v1 | Jev-first |
| --- | --- | --- | --- |
| Faithfulness | 0.876 | 0.861 | pending |
| Answer correctness | 0.739 | 0.748 | pending |
| Context precision | 0.864 | 0.861 | pending |
| Context recall | 0.874 | 0.862 | pending |
| LLM calls per question | 3.83 | 3.03 | pending |
| LLM tokens per question | 8,495 | 6,748 | pending |
| Jev decisions on the answer path, p50 / p95 | - | 282 / 361 ms | pending |
| Jev cost for 29 questions | - | $0.011 | pending |
| Questions answered | 29 of 29 | 29 of 29 | pending |
<!-- results:end -->

The baseline was judged three times; the spread of the run means is at most 0.033 (context recall) and about 0.01 for the other metrics, so the quality differences between the two finished runs are within the judge's noise. Jev v1 skipped the LLM sufficiency check on 19 of 29 questions.

Jev v1 rewrote every question with the LLM, asked Jev whether the fragments were enough and still called the LLM whenever Jev was below the threshold, so it saved about a fifth of the tokens. That was not enough to be worth it.

The first Jev-first variant (run `eval_gitlab_jev_first`, label `jev_first_a`, stopped at 17 of 29) went further: the question was searched as asked, Jev's verdict alone decided between answering and rewriting, and fragments below 0.5 were left out of the answer. On those 17 questions it used 2,397 tokens per question against 7,642 without Jev, but answer correctness fell from 0.749 to 0.660. Two causes were visible per question: Jev called the fragments insufficient (0.04) on a question the baseline answered well, and with no LLM check the answer came out empty; and needed secondary fragments graded 0.44-0.58 were dropped.

The current Jev-first keeps what did not cost quality: the first search uses the question as asked, a confident Jev answers without the LLM check, and the answer gets only the fragments Jev graded as needed, now above 0.3 and never fewer than the best two. When Jev is unsure the LLM check decides, as in Jev v1, whose quality matched the baseline. Its run is `eval_gitlab_jev_first2` (label `jev_first`). Like every run it uses the free Groq tier of the evaluation account, so it advances as the daily token limit allows; its first 3 answers came from the same model on the same Groq upstream reached through OpenRouter, before the evaluation went back to free Groq only.

### Running it

```bash
python app/eval/corpus/fetch_gitlab.py
python app/eval/run_eval.py app/eval/data/gitlab_dataset.json --docs app/eval/corpus/gitlab/*.md --serve jev --out eval_gitlab_jev_first.json
```

See [Development → Evaluation with ragas](development.md#evaluation-with-ragas) for `.env.eval`, the `eval` role and the GitHub Actions setup.
