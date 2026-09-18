import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from statistics import mean

import httpx

METRICS = ("faithfulness", "context_precision", "context_recall", "answer_correctness")
PENDING_STATUSES = ("queued", "processing")
INGEST_TIMEOUT_SECONDS = 300.0
POLL_SECONDS = 1.0


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


async def ask(client: httpx.AsyncClient, question: str) -> tuple[str, list[dict]]:
    answer, sources = "", []
    async with client.stream("POST", "/query", json={"question": question, "use_cache": False}) as response:
        if response.status_code != 200:
            raise RuntimeError(f"/query failed with {response.status_code}: {(await response.aread()).decode()}")
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = json.loads(line[len("data: ") :])
            if event["type"] == "token":
                answer += event["text"]
            elif event["type"] == "done":
                sources = event["sources"]
            elif event["type"] == "error":
                raise RuntimeError(f"/query stream error {event['status']}: {event['detail']}")
    return answer, sources


async def score(metrics: dict, item: dict, answer: str, contexts: list[str]) -> dict:
    question, reference = item["question"], item["reference"]
    results = await asyncio.gather(
        metrics["faithfulness"].ascore(user_input=question, response=answer, retrieved_contexts=contexts),
        metrics["context_precision"].ascore(user_input=question, reference=reference, retrieved_contexts=contexts),
        metrics["context_recall"].ascore(user_input=question, retrieved_contexts=contexts, reference=reference),
        metrics["answer_correctness"].ascore(user_input=question, response=answer, reference=reference),
    )
    return {name: float(result.value) for name, result in zip(METRICS, results)}


async def main() -> None:
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerCorrectness, ContextPrecision, ContextRecall, Faithfulness

    parser = argparse.ArgumentParser(description="Offline RAG quality evaluation with ragas")
    parser.add_argument("dataset", type=Path, help="JSON list of {question, reference}")
    parser.add_argument("--api", default=os.environ.get("GROUNDLINE_API", "http://localhost:8000"))
    parser.add_argument("--session", default=os.environ.get("GROUNDLINE_SESSION"), help="groundline_session cookie value")
    parser.add_argument("--docs", type=Path, nargs="*", default=[], help="Documents to upload before evaluation")
    parser.add_argument("--out", type=Path, default=Path("eval_results.json"))
    args = parser.parse_args()
    if not args.session:
        parser.error("--session or GROUNDLINE_SESSION is required")

    judge = llm_factory(
        os.environ.get("EVAL_LLM_MODEL", "openai/gpt-oss-120b"),
        provider="openai",
        client=AsyncOpenAI(
            api_key=os.environ["GROQ_API_KEY"],
            base_url=os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1"),
        ),
    )
    metrics = {
        "faithfulness": Faithfulness(llm=judge),
        "context_precision": ContextPrecision(llm=judge),
        "context_recall": ContextRecall(llm=judge),
        "answer_correctness": AnswerCorrectness(llm=judge, weights=[1.0, 0.0]),
    }
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))

    async with httpx.AsyncClient(
        base_url=args.api,
        headers={"X-Requested-With": "groundline"},
        cookies={"groundline_session": args.session},
        timeout=120,
    ) as client:
        for path in args.docs:
            await upload(client, path)
        rows = []
        for number, item in enumerate(dataset, start=1):
            answer, sources = await ask(client, item["question"])
            scores = await score(metrics, item, answer, [source["content"] for source in sources])
            rows.append({**item, "answer": answer, "sources": sources, "scores": scores})
            print(f"[{number}/{len(dataset)}] " + "  ".join(f"{k}={v:.2f}" for k, v in scores.items()))

    summary = {name: round(mean(row["scores"][name] for row in rows), 4) for name in METRICS}
    args.out.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nsummary")
    for name, value in summary.items():
        print(f"  {name:<20} {value:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
