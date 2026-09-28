import json
import sys
from pathlib import Path

START = "<!-- results:start -->"
END = "<!-- results:end -->"
COLUMNS = (
    ("Without Jev", "eval_gitlab_baseline.json"),
    ("Jev v1", "eval_gitlab_jev.json"),
    ("Jev-first", "eval_gitlab_jev_first2.json"),
)
QUALITY = (
    ("Faithfulness", "faithfulness"),
    ("Answer correctness", "answer_correctness"),
    ("Context precision", "context_precision"),
    ("Context recall", "context_recall"),
)


def _number(value, digits: int = 3) -> str:
    return "pending" if value is None else f"{value:.{digits}f}"


def cells(run: dict | None) -> dict[str, str]:
    if not run or not run.get("rows"):
        return {}
    summary = run["summary"]
    every = summary["all"]
    questions = every["questions"]
    critical = summary["jev_latency"]["critical"]
    row = {label: _number(every[key]) for label, key in QUALITY}
    row["LLM calls per question"] = f"{every['groq_calls'] / questions:.2f}"
    row["LLM tokens per question"] = f"{every['groq_tokens'] / questions:,.0f}"
    row["Jev decisions on the answer path, p50 / p95"] = (
        f"{critical['p50_ms']} / {critical['p95_ms']} ms" if critical["calls"] else "-"
    )
    cost = run.get("jev_cost_usd")
    row[f"Jev cost for {questions} questions"] = f"${cost:.3f}" if cost else "-"
    row["Questions answered"] = f"{questions} of {run.get('total_questions') or questions}"
    return row


def table(runs: dict[str, dict | None]) -> str:
    columns = {name: cells(run) for name, run in runs.items()}
    labels = [label for label, _ in QUALITY] + [
        "LLM calls per question",
        "LLM tokens per question",
        "Jev decisions on the answer path, p50 / p95",
    ]
    labels += sorted({label for row in columns.values() for label in row if label.startswith("Jev cost")})
    labels.append("Questions answered")
    lines = ["| | " + " | ".join(columns) + " |", "| --- |" + " --- |" * len(columns)]
    for label in labels:
        lines.append(f"| {label} | " + " | ".join(row.get(label, "pending") for row in columns.values()) + " |")
    return "\n".join(lines)


def publish(document: Path, folder: Path) -> bool:
    runs = {}
    for name, file in COLUMNS:
        path = folder / file
        runs[name] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    text = document.read_text(encoding="utf-8")
    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    updated = f"{head}{START}\n{table(runs)}\n{END}{tail}"
    if updated == text:
        return False
    document.write_text(updated, encoding="utf-8")
    return True


if __name__ == "__main__":
    changed = publish(Path(sys.argv[1]), Path(sys.argv[2] if len(sys.argv) > 2 else "."))
    print("results updated" if changed else "results unchanged")
