import argparse
import asyncio
import contextlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean, median, pstdev

import httpx

ROOT = Path(__file__).resolve().parents[2]
EVAL_ENV = ROOT / ".env.eval"
SERVER_LOG = ROOT / "eval_server.log"
METRICS = ("faithfulness", "context_precision", "context_recall", "answer_correctness")
LLM_NODES = ("rewrite_query", "check_sufficiency", "generate_answer")
CRITICAL_JEV_NODES = ("check_cache", "jev_sufficiency")
LATENCY_NODES = ("check_cache", "jev_sufficiency", "check_sufficiency", "generate_answer")
PENDING_STATUSES = ("queued", "processing")
INGEST_TIMEOUT_SECONDS = 300.0
SERVER_START_SECONDS = 900.0
POLL_SECONDS = 1.0
TRANSIENT_RETRIES = 5
TRANSIENT_WAIT_SECONDS = 60.0
JUDGE_ATTEMPTS = 3
DAILY_LIMIT_MARKERS = ("tokens per day", "requests per day")


JUDGE_ENDPOINTS = {
    "groq": ("GROQ_API_KEY", "https://api.groq.com/openai/v1"),
    "openrouter": ("OPENROUTER_API_KEY", "https://openrouter.ai/api/v1"),
}


class DailyLimitReached(RuntimeError):
    pass


class PinnedUpstream(httpx.AsyncBaseTransport):
    def __init__(self, upstream: str, inner: httpx.AsyncBaseTransport | None = None) -> None:
        self.upstream = upstream
        self.inner = inner or httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/chat/completions"):
            body = json.loads(await request.aread())
            body["provider"] = {"order": [self.upstream], "allow_fallbacks": False}
            headers = [(key, value) for key, value in request.headers.items() if key.lower() != "content-length"]
            request = httpx.Request(request.method, request.url, headers=headers, json=body)
        return await self.inner.handle_async_request(request)

    async def aclose(self) -> None:
        await self.inner.aclose()


class JudgeMeter:
    def __init__(self) -> None:
        self.cost = 0.0
        self.upstreams: dict[str, int] = {}

    async def __call__(self, response: httpx.Response) -> None:
        if response.status_code != 200 or not response.request.url.path.endswith("/chat/completions"):
            return
        await response.aread()
        try:
            body = response.json()
        except ValueError:
            return
        self.cost += float((body.get("usage") or {}).get("cost") or 0.0)
        upstream = body.get("provider") or "unknown"
        self.upstreams[upstream] = self.upstreams.get(upstream, 0) + 1


class TransientError(RuntimeError):
    pass


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def eval_settings() -> dict[str, str]:
    return {**read_env(ROOT / ".env"), **read_env(EVAL_ENV), **os.environ}


async def wait_for_job(client: httpx.AsyncClient, job: dict, timeout: float = INGEST_TIMEOUT_SECONDS) -> dict:
    deadline = time.monotonic() + timeout
    while job["status"] in PENDING_STATUSES:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"indexing {job['filename']} did not finish within {timeout:.0f}s")
        await asyncio.sleep(POLL_SECONDS)
        response = await client.get(f"/jobs/{job['id']}")
        response.raise_for_status()
        job = response.json()
    if job["status"] != "done":
        raise RuntimeError(f"indexing {job['filename']} failed: {job.get('error') or 'unknown error'}")
    return job


async def chunk_count(client: httpx.AsyncClient, document_id: str | None) -> int | None:
    if document_id is None:
        return None
    response = await client.get("/documents")
    response.raise_for_status()
    return next((item["chunk_count"] for item in response.json() if item["id"] == document_id), None)


async def upload(client: httpx.AsyncClient, path: Path) -> None:
    response = await client.post("/ingest", files={"file": (path.name, path.read_bytes())})
    response.raise_for_status()
    job = await wait_for_job(client, response.json())
    chunks = await chunk_count(client, job.get("document_id"))
    print(f"indexed {path.name}: {chunks if chunks is not None else 'unknown'} chunks")


async def ensure_documents(client: httpx.AsyncClient, paths: list[Path]) -> None:
    response = await client.get("/documents")
    response.raise_for_status()
    indexed = {item["filename"] for item in response.json() if item["chunk_count"]}
    for path in paths:
        if path.name in indexed:
            print(f"already indexed {path.name}")
        else:
            await upload(client, path)


async def ask(client: httpx.AsyncClient, question: str, use_cache: bool = False) -> dict:
    started = time.perf_counter()
    run = {"answer": "", "sources": [], "done": None, "grounding": None, "first_token_ms": None, "done_ms": None}

    def elapsed() -> int:
        return round((time.perf_counter() - started) * 1000)

    async with client.stream("POST", "/query", json={"question": question, "use_cache": use_cache}) as response:
        if response.status_code != 200:
            detail = (await response.aread()).decode()
            if response.status_code == 429 and "limit reached" in detail:
                raise DailyLimitReached(detail)
            if response.status_code in (502, 504):
                raise TransientError(f"/query failed with {response.status_code}: {detail}")
            raise RuntimeError(f"/query failed with {response.status_code}: {detail}")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event["type"] == "token":
                if run["first_token_ms"] is None:
                    run["first_token_ms"] = elapsed()
                run["answer"] += event["text"]
            elif event["type"] == "done":
                run["done"], run["sources"], run["done_ms"] = event, event["sources"], elapsed()
            elif event["type"] == "grounding":
                run["grounding"] = event
            elif event["type"] == "error":
                if event["status"] == 429 and "limit reached" in event["detail"]:
                    raise DailyLimitReached(event["detail"])
                raise TransientError(f"/query stream error {event['status']}: {event['detail']}")
    run["end_ms"] = elapsed()
    return run


async def ask_patiently(client: httpx.AsyncClient, question: str, use_cache: bool = False) -> dict:
    for attempt in range(TRANSIENT_RETRIES):
        try:
            return await ask(client, question, use_cache)
        except TransientError as exc:
            if attempt == TRANSIENT_RETRIES - 1:
                raise
            print(f"  {exc}, retrying in {TRANSIENT_WAIT_SECONDS:.0f}s")
            await asyncio.sleep(TRANSIENT_WAIT_SECONDS)
    raise AssertionError("unreachable")


async def last_metrics(client: httpx.AsyncClient) -> list[dict]:
    response = await client.get("/history", params={"limit": 1})
    response.raise_for_status()
    rows = response.json()
    return rows[0]["node_metrics"] if rows else []


def run_facts(metrics: list[dict]) -> dict:
    jev: dict[str, dict] = {}
    node_ms: dict[str, int] = {}
    for metric in metrics:
        if "jev" in metric:
            jev.setdefault(metric["node"], metric["jev"])
        node_ms[metric["node"]] = node_ms.get(metric["node"], 0) + metric["duration_ms"]
    return {
        "groq_calls": sum(1 for metric in metrics if metric["node"] in LLM_NODES and metric["tokens"] > 0),
        "jev": jev,
        "node_ms": node_ms,
    }


async def jev_spend(client: httpx.AsyncClient) -> float | None:
    response = await client.get("/limits")
    response.raise_for_status()
    return next(
        (service["used"] for service in response.json()["services"] if service["key"] == "jev.spend_per_month"), None
    )


async def jev_enabled(client: httpx.AsyncClient) -> bool:
    response = await client.get("/config")
    response.raise_for_status()
    return "jev_sufficiency" in response.json().get("pipeline_nodes", [])


def mean_of(values) -> float | None:
    present = [value for value in values if value is not None and value == value]
    return round(mean(present), 4) if present else None


def percentile(values: list[float], share: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    return ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)]


def latencies(rows: list[dict], nodes: tuple[str, ...]) -> list[int]:
    return [row["jev"][node]["latency_ms"] for row in rows for node in nodes if "latency_ms" in row["jev"].get(node, {})]


def latency_summary(values: list[int]) -> dict:
    return {
        "calls": len(values),
        "p50_ms": percentile(values, 0.5),
        "p95_ms": percentile(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def summarize(rows: list[dict]) -> dict:
    return {
        "questions": len(rows),
        **{name: mean_of(row["scores"][name] for row in rows) for name in METRICS},
        "groq_calls": sum(row["groq_calls"] for row in rows),
        "groq_tokens": sum(row["tokens_used"] for row in rows),
        "done_ms_mean": mean_of(row["done_ms"] for row in rows),
        "done_ms_median": median(row["done_ms"] for row in rows) if rows else None,
        "end_ms_mean": mean_of(row["end_ms"] for row in rows),
        "jev_sufficient_passed": sum(1 for row in rows if row["jev"].get("jev_sufficiency", {}).get("passed")),
        "jev_failed": sum(1 for row in rows for trace in row["jev"].values() if trace.get("failed")),
        "unscored_metrics": sum(1 for row in rows for value in row["scores"].values() if value is None),
        "judge_cost_usd": round(sum(row.get("judge_cost_usd") or 0.0 for row in rows), 6),
    }


def score_runs(row: dict) -> list[dict]:
    return row.get("score_runs") or [row["scores"]]


def question_range(row: dict, name: str) -> float | None:
    values = [run[name] for run in score_runs(row) if run[name] is not None]
    return round(max(values) - min(values), 4) if values else None


def judge_spread(rows: list[dict]) -> dict:
    runs = min((len(score_runs(row)) for row in rows), default=0)
    metrics = {}
    for name in METRICS:
        run_means = [mean_of(score_runs(row)[index][name] for row in rows) for index in range(runs)]
        present = [value for value in run_means if value is not None]
        metrics[name] = {
            "run_means": run_means,
            "std": round(pstdev(present), 4) if len(present) > 1 else 0.0,
            "mean_question_range": mean_of(question_range(row, name) for row in rows),
        }
    return {"runs": runs, "metrics": metrics}


def node_latency(rows: list[dict]) -> dict:
    latency = {}
    for node in LATENCY_NODES:
        values = [row["node_ms"][node] for row in rows if node in row.get("node_ms", {})]
        if values:
            latency[node] = {"calls": len(values), "median_ms": median(values), "p95_ms": percentile(values, 0.95)}
    return latency


def grouped(rows: list[dict], field: str) -> dict:
    return {value: summarize([row for row in rows if row[field] == value]) for value in sorted({row[field] for row in rows})}


def summary_of(rows: list[dict], pairs: list[dict]) -> dict:
    critical = latencies(rows, CRITICAL_JEV_NODES) + [pair["jev_latency_ms"] for pair in pairs if pair["jev_latency_ms"]]
    return {
        "all": summarize(rows),
        "lang": grouped(rows, "lang"),
        "kind": grouped(rows, "kind"),
        "jev_latency": {
            "critical": latency_summary(critical),
            "grounding": latency_summary(latencies(rows, ("check_grounding",))),
        },
        "node_latency": node_latency(rows),
        "judge_spread": judge_spread(rows),
    }


async def cache_pairs(client: httpx.AsyncClient, dataset: list[dict], done: list[dict], save) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for item in dataset:
        if item.get("pair"):
            groups.setdefault(item["pair"], []).append(item)
    finished = {pair["pair"] for pair in done}
    results = list(done)
    for name, items in groups.items():
        if name in finished:
            continue
        (await client.delete("/cache")).raise_for_status()
        anchor = next(item for item in items if item["role"] == "anchor")
        await ask_patiently(client, anchor["question"], use_cache=True)
        group = []
        for item in items:
            if item is anchor:
                continue
            run = await ask_patiently(client, item["question"], use_cache=True)
            check_cache = run_facts(await last_metrics(client))["jev"].get("check_cache", {})
            hit = run["done"]["cache_hit"]
            group.append(
                {
                    "pair": name,
                    "role": item["role"],
                    "question": item["question"],
                    "cache_hit": hit,
                    "similarity": run["done"]["cache_similarity"],
                    "jev_same_question": check_cache.get("same_question"),
                    "jev_latency_ms": check_cache.get("latency_ms"),
                    "correct": hit == (item["role"] == "paraphrase"),
                }
            )
            print(f"cache {name}/{item['role']}: {'HIT ' if hit else 'MISS'} similarity={group[-1]['similarity']}")
        results += group
        save(results)
    (await client.delete("/cache")).raise_for_status()
    return results


async def judged(name: str, attempt_score) -> float | None:
    for attempt in range(1, JUDGE_ATTEMPTS + 1):
        try:
            return float((await attempt_score()).value)
        except Exception as exc:
            if any(marker in str(exc) for marker in DAILY_LIMIT_MARKERS):
                raise DailyLimitReached(f"the judge is out of its daily quota: {str(exc)[:300]}") from exc
            print(f"  judge failed on {name} ({attempt}/{JUDGE_ATTEMPTS}): {str(exc)[:160]}")
    return None


async def score(metrics: dict, item: dict, answer: str, contexts: list[str]) -> dict:
    question, reference = item["question"], item["reference"]
    calls = {
        "faithfulness": lambda: metrics["faithfulness"].ascore(
            user_input=question, response=answer, retrieved_contexts=contexts
        ),
        "context_precision": lambda: metrics["context_precision"].ascore(
            user_input=question, reference=reference, retrieved_contexts=contexts
        ),
        "context_recall": lambda: metrics["context_recall"].ascore(
            user_input=question, retrieved_contexts=contexts, reference=reference
        ),
        "answer_correctness": lambda: metrics["answer_correctness"].ascore(
            user_input=question, response=answer, reference=reference
        ),
    }
    results = await asyncio.gather(*(judged(name, calls[name]) for name in METRICS))
    return dict(zip(METRICS, results))


def server_python() -> str:
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    return sys.executable


@contextlib.asynccontextmanager
async def serve(port: int, overrides: dict[str, str]):
    environment = {**os.environ, **read_env(EVAL_ENV), **overrides}
    log = SERVER_LOG.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [server_python(), "-m", "uvicorn", "app.api.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=environment,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + SERVER_START_SECONDS
        async with httpx.AsyncClient(base_url=url, headers={"X-Requested-With": "groundline"}) as probe:
            while True:
                if process.poll() is not None:
                    raise RuntimeError(f"the API exited with {process.returncode} while starting")
                with contextlib.suppress(httpx.HTTPError):
                    if (await probe.get("/health")).status_code == 200:
                        break
                if time.monotonic() >= deadline:
                    raise RuntimeError("the API did not start in time")
                await asyncio.sleep(2)
        yield url
    finally:
        process.terminate()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=30)
        log.close()


async def main() -> None:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerCorrectness, ContextPrecision, ContextRecall, Faithfulness

    parser = argparse.ArgumentParser(description="Offline RAG quality evaluation with ragas")
    parser.add_argument("dataset", type=Path, help="JSON list of {question, reference, kind?, lang?, pair?, role?}")
    parser.add_argument("--api", default=os.environ.get("GROUNDLINE_API", "http://localhost:8000"))
    parser.add_argument("--session", default=os.environ.get("GROUNDLINE_SESSION"), help="groundline_session cookie value")
    parser.add_argument("--docs", type=Path, nargs="*", default=[], help="Documents to index before evaluation")
    parser.add_argument("--out", type=Path, default=Path("eval_results.json"))
    parser.add_argument("--label", help="name of this run in the comparison, defaults to jev or baseline")
    parser.add_argument(
        "--cache-pairs", action="store_true", help="also check paraphrase and look-alike pairs against the cache"
    )
    parser.add_argument(
        "--serve",
        choices=("jev", "baseline"),
        help="start the API with .env plus .env.eval and JEV_ENABLED set for this run, instead of using --api",
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="extra server setting")
    parser.add_argument("--fresh", action="store_true", help="discard a partial result file instead of resuming it")
    parser.add_argument(
        "--rescore", action="store_true", help="re-judge stored answers from another judge instead of refusing to resume"
    )
    parser.add_argument(
        "--judge-repeats", type=int, default=1, help="judge every stored answer this many times and average the scores"
    )
    args = parser.parse_args()
    if not args.session:
        parser.error("--session or GROUNDLINE_SESSION is required")

    config = eval_settings()
    judge_provider = config.get("EVAL_JUDGE_PROVIDER", "groq")
    key_name, base_url = JUDGE_ENDPOINTS[judge_provider]
    judge_model = config.get("EVAL_LLM_MODEL", "openai/gpt-oss-120b")
    judge_upstream = config.get("EVAL_JUDGE_UPSTREAM") if judge_provider == "openrouter" else None
    judge_max_tokens = int(config.get("EVAL_JUDGE_MAX_TOKENS", "4096"))
    judge_id = (
        f"{judge_provider}:{judge_model}"
        + (f"@{judge_upstream}" if judge_upstream else "")
        + f",max_tokens={judge_max_tokens}"
    )
    meter = JudgeMeter()
    judge = llm_factory(
        judge_model,
        provider="openai",
        max_tokens=judge_max_tokens,
        client=AsyncOpenAI(
            api_key=config[key_name],
            base_url=base_url,
            max_retries=8,
            http_client=httpx.AsyncClient(
                timeout=120,
                event_hooks={"response": [meter]},
                transport=PinnedUpstream(judge_upstream) if judge_upstream else None,
            ),
        ),
    )
    metrics = {
        "faithfulness": Faithfulness(llm=judge),
        "context_precision": ContextPrecision(llm=judge),
        "context_recall": ContextRecall(llm=judge),
        "answer_correctness": AnswerCorrectness(llm=judge, weights=[1.0, 0.0]),
    }
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    questions = [item for item in dataset if item.get("kind") != "cache_pair"]
    previous = {}
    if args.out.exists() and not args.fresh:
        previous = json.loads(args.out.read_text(encoding="utf-8"))
        extends = args.judge_repeats > 1 or (args.cache_pairs and not previous.get("cache_pairs"))
        if previous.get("complete") and not extends:
            parser.error(f"{args.out} holds a finished run, pass --fresh to replace it")
        if previous.get("judge") != judge_id and not args.rescore:
            parser.error(
                f"{args.out} was judged by {previous.get('judge')}, not {judge_id}: resume it with the same judge "
                "or pass --rescore to re-judge the stored answers"
            )
        print(f"resuming {args.out}: {len(previous['rows'])} questions and {len(previous['cache_pairs'])} pairs done")
    rows: list[dict] = previous.get("rows", [])
    pairs: list[dict] = previous.get("cache_pairs", [])
    spent: float = previous.get("jev_cost_usd") or 0.0
    for row in rows:
        row.setdefault("judge", previous.get("judge"))
    upstreams: dict[str, int] = dict(previous.get("judge_upstreams") or {})

    async def judged_row(item: dict, answer: str, sources: list[dict]) -> dict:
        before, seen = meter.cost, dict(meter.upstreams)
        scores = await score(metrics, item, answer, [source["content"] for source in sources])
        for upstream, count in meter.upstreams.items():
            upstreams[upstream] = upstreams.get(upstream, 0) + count - seen.get(upstream, 0)
        return {"scores": scores, "judge": judge_id, "judge_cost_usd": round(meter.cost - before, 6)}

    overrides = dict(item.split("=", 1) for item in args.set)
    if args.serve:
        overrides["JEV_ENABLED"] = "true" if args.serve == "jev" else "false"
    run_settings = previous.get("settings", overrides)
    pair_settings = overrides if args.cache_pairs else previous.get("pair_settings")
    server = serve(args.port, overrides) if args.serve else contextlib.nullcontext(args.api)

    async with server as api, httpx.AsyncClient(
        base_url=api,
        headers={"X-Requested-With": "groundline"},
        cookies={"groundline_session": args.session},
        timeout=120,
    ) as client:
        with_jev = await jev_enabled(client)
        label = args.label or ("jev" if with_jev else "baseline")

        def save(complete: bool = False) -> None:
            result = {
                "label": label,
                "jev": with_jev,
                "judge": judge_id,
                "judge_upstreams": upstreams,
                "settings": run_settings,
                "pair_settings": pair_settings,
                "complete": complete,
                "jev_cost_usd": round(spent, 6) if with_jev else None,
                "summary": summary_of(rows, pairs),
                "cache_pairs": pairs,
                "rows": rows,
            }
            args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        await ensure_documents(client, args.docs)
        (await client.delete("/cache")).raise_for_status()
        try:
            for number, row in enumerate(rows, start=1):
                if row["judge"] != judge_id:
                    row.update(await judged_row(row, row["answer"], row["sources"]))
                    row["score_runs"] = [row["scores"]]
                    save()
                    print(f"re-judged [{number}/{len(rows)}] {row['scores']}")
            for number, item in enumerate(questions, start=1):
                if number <= len(rows):
                    if rows[number - 1]["question"] != item["question"]:
                        raise RuntimeError(f"{args.out} does not match the dataset at question {number}, use --fresh")
                    continue
                before = await jev_spend(client)
                run = await ask_patiently(client, item["question"])
                after = await jev_spend(client)
                if before is not None and after is not None:
                    spent += after - before
                facts = run_facts(await last_metrics(client))
                judgement = await judged_row(item, run["answer"], run["sources"])
                scores = judgement["scores"]
                rows.append(
                    {
                        **item,
                        "kind": item.get("kind", "answerable"),
                        "lang": item.get("lang", "en"),
                        "answer": run["answer"],
                        "sources": run["sources"],
                        **judgement,
                        "score_runs": [scores],
                        "tokens_used": run["done"]["tokens_used"],
                        "first_token_ms": run["first_token_ms"],
                        "done_ms": run["done_ms"],
                        "end_ms": run["end_ms"],
                        "grounding": run["grounding"],
                        **facts,
                    }
                )
                save()
                print(f"[{number}/{len(questions)}] " + "  ".join(f"{k}={v if v is None else round(v, 2)}" for k, v in scores.items()))
            for number, row in enumerate(rows, start=1):
                runs = row.setdefault("score_runs", [row["scores"]])
                if len(runs) >= args.judge_repeats:
                    continue
                while len(runs) < args.judge_repeats:
                    judgement = await judged_row(row, row["answer"], row["sources"])
                    runs.append(judgement["scores"])
                    row["judge_cost_usd"] = round((row.get("judge_cost_usd") or 0.0) + judgement["judge_cost_usd"], 6)
                row["scores"] = {name: mean_of(run[name] for run in runs) for name in METRICS}
                save()
                print(f"judged x{len(runs)} [{number}/{len(rows)}] {row['scores']}")
            if args.cache_pairs:

                def save_pairs(results: list[dict]) -> None:
                    pairs[:] = results
                    save()

                await cache_pairs(client, dataset, pairs, save_pairs)
        except DailyLimitReached as exc:
            save()
            raise SystemExit(f"stopped: {exc}\nrun the same command again after the reset to continue from here")
        save(complete=True)

    summary = summary_of(rows, pairs)
    print("\nsummary")
    for name, value in summary["all"].items():
        print(f"  {name:<24} {value}")
    print(f"  {'jev_latency':<24} {summary['jev_latency']}")
    if with_jev:
        print(f"  {'jev_cost_usd':<24} {round(spent, 6)}")
    if pairs:
        print(f"  {'cache_pairs_correct':<24} {sum(pair['correct'] for pair in pairs)}/{len(pairs)}")


if __name__ == "__main__":
    asyncio.run(main())
