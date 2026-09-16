import argparse
import json
import os
import sys
from pathlib import Path

import httpx


def ask(client: httpx.Client, question: str) -> dict:
    with client.stream("POST", "/query", json={"question": question}) as response:
        if response.status_code != 200:
            raise SystemExit(f"/query failed with {response.status_code}: {response.read().decode()}")
        for line in response.iter_lines():
            if line.startswith("data: "):
                event = json.loads(line[len("data: ") :])
                if event["type"] == "done":
                    return event
                if event["type"] == "error":
                    raise SystemExit(f"/query stream error {event['status']}: {event['detail']}")
    raise SystemExit("stream ended without a done event")


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure semantic cache similarity for a list of questions")
    parser.add_argument("questions", type=Path, help="text file, one question per line, or JSON list of strings")
    parser.add_argument("--api", default=os.environ.get("GROUNDLINE_API", "http://localhost:8000"))
    parser.add_argument("--session", default=os.environ.get("GROUNDLINE_SESSION"))
    args = parser.parse_args()
    if not args.session:
        parser.error("--session or GROUNDLINE_SESSION is required")

    raw = args.questions.read_text(encoding="utf-8").strip()
    questions = json.loads(raw) if raw.startswith("[") else [line for line in raw.splitlines() if line.strip()]

    rows = []
    with httpx.Client(
        base_url=args.api,
        headers={"X-Requested-With": "groundline"},
        cookies={"groundline_session": args.session},
        timeout=120,
    ) as client:
        for question in questions:
            done = ask(client, question)
            rows.append(
                {
                    "question": question,
                    "similarity": done.get("cache_similarity"),
                    "threshold": done.get("cache_threshold"),
                    "cache_hit": done["cache_hit"],
                    "tokens_used": done["tokens_used"],
                    "tokens_saved": done["tokens_saved"],
                }
            )
            similarity = "no-entries" if rows[-1]["similarity"] is None else f"{rows[-1]['similarity']:.4f}"
            print(f"{'HIT ' if done['cache_hit'] else 'MISS'}  similarity={similarity}  {question}")

    measured = [row["similarity"] for row in rows if row["similarity"] is not None]
    if measured:
        hits = [row["similarity"] for row in rows if row["cache_hit"]]
        misses = [row["similarity"] for row in rows if not row["cache_hit"] and row["similarity"] is not None]
        print(f"\nthreshold in use: {rows[0]['threshold']}")
        print(f"hits   : {len(hits)}  similarity range {min(hits, default=0):.4f}..{max(hits, default=0):.4f}")
        print(f"misses : {len(misses)}  similarity range {min(misses, default=0):.4f}..{max(misses, default=0):.4f}")
        print("\nRaise the threshold above the highest wrong hit, lower it below the lowest correct miss.")
    json.dump(rows, sys.stdout, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
