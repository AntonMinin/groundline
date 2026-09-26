import argparse
import json
from pathlib import Path

from app.eval.run_eval import LATENCY_NODES, METRICS, question_range


def per_question(summary: dict, key: str) -> float | None:
    return round(summary[key] / summary["questions"], 2) if summary["questions"] else None


def cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:,.6g}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def pairs_correct(result: dict) -> str | None:
    pairs = result["cache_pairs"]
    return f"{sum(pair['correct'] for pair in pairs)}/{len(pairs)}" if pairs else None


def spread(result: dict, name: str) -> str | float | None:
    value = result["summary"]["all"][name]
    judged = result["summary"].get("judge_spread", {})
    if value is None or judged.get("runs", 1) < 2:
        return value
    return f"{value:.4f} ± {judged['metrics'][name]['std']:.4f}"


def question_changes(baseline: dict, candidate: dict) -> list[str]:
    before = {row["question"]: row for row in baseline["rows"]}
    counts = {name: {"better": 0, "worse": 0, "same": 0} for name in METRICS}
    for row in candidate["rows"]:
        other = before.get(row["question"])
        if other is None:
            continue
        for name in METRICS:
            left, right = other["scores"][name], row["scores"][name]
            if left is None or right is None:
                continue
            tolerance = ((question_range(other, name) or 0.0) + (question_range(row, name) or 0.0)) / 2
            if abs(right - left) <= tolerance or right == left:
                counts[name]["same"] += 1
            elif right > left:
                counts[name]["better"] += 1
            else:
                counts[name]["worse"] += 1
    header = [f"| Metric | {candidate['label']} better | {candidate['label']} worse | no change |", "| --- | ---: | ---: | ---: |"]
    return header + [
        f"| {name} | {counts[name]['better']} | {counts[name]['worse']} | {counts[name]['same']} |" for name in METRICS
    ]


def lines(baseline: dict, candidate: dict) -> list[str]:
    rows: list[tuple[str, object, object]] = []
    scopes = [("all", lambda result: result["summary"]["all"])]
    for group in ("lang", "kind"):
        for value in sorted(baseline["summary"][group]):
            scopes.append((value, lambda result, group=group, value=value: result["summary"][group].get(value)))
    for scope, pick in scopes:
        left, right = pick(baseline), pick(candidate)
        if not left or not right:
            continue
        for name in METRICS:
            if scope == "all":
                rows.append((f"{name} ({scope}, n={left['questions']})", spread(baseline, name), spread(candidate, name)))
            else:
                rows.append((f"{name} ({scope}, n={left['questions']})", left[name], right[name]))
    left, right = baseline["summary"]["all"], candidate["summary"]["all"]
    for node in LATENCY_NODES:
        for key in ("median_ms", "p95_ms"):
            rows.append(
                (
                    f"`{node}` {key.removesuffix('_ms')} ms",
                    baseline["summary"].get("node_latency", {}).get(node, {}).get(key),
                    candidate["summary"].get("node_latency", {}).get(node, {}).get(key),
                )
            )
    rows += [
        ("Groq calls per question", per_question(left, "groq_calls"), per_question(right, "groq_calls")),
        ("Groq tokens per question", per_question(left, "groq_tokens"), per_question(right, "groq_tokens")),
        ("Groq tokens total", left["groq_tokens"], right["groq_tokens"]),
        ("time to `done`, mean ms", left["done_ms_mean"], right["done_ms_mean"]),
        ("time to `done`, median ms", left["done_ms_median"], right["done_ms_median"]),
        ("time to end of stream, mean ms", left["end_ms_mean"], right["end_ms_mean"]),
        ("LLM sufficiency checks skipped by Jev", left["jev_sufficient_passed"], right["jev_sufficient_passed"]),
        ("Jev cost, USD", baseline["jev_cost_usd"], candidate["jev_cost_usd"]),
        ("judge cost (ragas), USD", left["judge_cost_usd"], right["judge_cost_usd"]),
        ("Jev calls that failed open", left["jev_failed"], right["jev_failed"]),
        ("ragas metrics the judge could not score", left["unscored_metrics"], right["unscored_metrics"]),
    ]
    for path, title in (("critical", "Jev latency before the answer"), ("grounding", "Jev latency of check_grounding")):
        for key in ("p50_ms", "p95_ms", "max_ms"):
            rows.append(
                (
                    f"{title}, {key.removesuffix('_ms')} ms",
                    baseline["summary"]["jev_latency"][path][key],
                    candidate["summary"]["jev_latency"][path][key],
                )
            )
    rows.append(("cache pairs decided correctly", pairs_correct(baseline), pairs_correct(candidate)))
    header = [f"| Metric | {baseline['label']} | {candidate['label']} |", "| --- | ---: | ---: |"]
    return header + [f"| {name} | {cell(left)} | {cell(right)} |" for name, left, right in rows]


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown table comparing two run_eval.py result files")
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    args = parser.parse_args()
    baseline, candidate = (json.loads(path.read_text(encoding="utf-8")) for path in (args.baseline, args.candidate))
    print("\n".join(lines(baseline, candidate)))
    print()
    print("\n".join(question_changes(baseline, candidate)))


if __name__ == "__main__":
    main()
