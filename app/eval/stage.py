import json
import sys
from pathlib import Path

JUDGE_REPEATS = 3


def answered(run: dict) -> bool:
    total = run.get("total_questions")
    return total is not None and len(run.get("rows") or []) >= total


def finished(run: dict) -> bool:
    return (
        answered(run)
        and run.get("complete", False)
        and bool(run.get("cache_pairs"))
        and all(len(row.get("score_runs") or []) >= JUDGE_REPEATS for row in run["rows"])
    )


STAGES = {"answered": answered, "finished": finished}


def reached(path: Path, stage: str) -> bool:
    return path.exists() and STAGES[stage](json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    sys.exit(0 if reached(Path(sys.argv[1]), sys.argv[2]) else 1)
