"""The results ledger: build, validate, read and write run records.

The contract lives in ``results/README.md`` and is deliberately frozen ahead
of the harness port: results key on case ``uid`` + ``caseset_version``,
checks are tri-state (``1.0`` / ``0.0`` / ``None``), and nothing is ever
hand-written into the ledger.

Naming quirk handled here once: the gnw-evals CSVs call the score
``charts_answer_score`` but its reason column ``chart_answer_score_reason``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RUNS_DIRNAME = "runs"

# reason-column stem -> check name (gnw-evals historical inconsistency)
REASON_ALIASES = {"chart_answer": "charts_answer"}

# score columns that are aggregates or diagnostics, not checks
NON_CHECK_SCORES = {"overall_score"}

_RUN_ID_RE = re.compile(r"^\d{8}T\d{6}Z_[a-z]+(_[a-z0-9-]+)?$")

REQUIRED_RUN_FIELDS = (
    "run_id",
    "started",
    "environment",
    "build",
    "ff",
    "harness",
    "judge_model",
    "num_trials",
    "caseset_version",
    "results",
)


def check_name_from_column(column: str) -> str | None:
    """Map a harness CSV column to a check name, or None if not a check."""
    if column in NON_CHECK_SCORES or column.endswith("_score_std"):
        return None
    if column.endswith("_score"):
        return column.removesuffix("_score")
    return None


def reason_name_from_column(column: str) -> str | None:
    if column.endswith("_score_reason"):
        stem = column.removesuffix("_score_reason")
        return REASON_ALIASES.get(stem, stem)
    if column.endswith("_reason"):
        # deterministic validators write plain <check>_reason fields
        return column.removesuffix("_reason")
    return None


def parse_score(cell: object) -> float | None:
    """Tri-state parse: empty -> None (not evaluated), else 1.0/0.0."""
    text = str(cell or "").strip()
    if not text:
        return None
    value = float(text)
    if value not in (0.0, 1.0):
        raise ValueError(f"check scores must be binary, got {value!r}")
    return value


def majority(values: list[float | None]) -> float | None:
    """Majority verdict across trials. None if never evaluated; ties fail
    conservatively."""
    evaluated = [v for v in values if v is not None]
    if not evaluated:
        return None
    passes = sum(1 for v in evaluated if v == 1.0)
    return 1.0 if passes * 2 > len(evaluated) else 0.0


def make_run_id(started_utc: str, environment: str, ff: str | None) -> str:
    """``<YYYYMMDD>T<HHMMSS>Z_<env>[_<ff>]`` from an ISO-8601 UTC timestamp."""
    compact = re.sub(r"[-:]", "", started_utc.split(".")[0]).removesuffix("Z")
    if not re.fullmatch(r"\d{8}T\d{6}", compact):
        raise ValueError(f"cannot derive run_id from started={started_utc!r}")
    run_id = f"{compact}Z_{environment}"
    if ff:
        run_id += f"_{ff}"
    return run_id


def validate_run(run: dict) -> list[str]:
    """Contract violations; empty list means the record is well-formed."""
    problems = [f"missing field: {f}" for f in REQUIRED_RUN_FIELDS if f not in run]
    if problems:
        return problems
    if not _RUN_ID_RE.match(run["run_id"]):
        problems.append(f"malformed run_id: {run['run_id']!r}")
    if not isinstance(run["results"], list) or not run["results"]:
        problems.append("results must be a non-empty list")
        return problems
    for i, entry in enumerate(run["results"]):
        label = entry.get("id") or f"results[{i}]"
        if not entry.get("uid") and not entry.get("stale_case"):
            problems.append(f"{label}: no uid and not marked stale_case")
        if "checks" not in entry or not isinstance(entry["checks"], dict):
            problems.append(f"{label}: missing checks mapping")
            continue
        for name, value in entry["checks"].items():
            if value not in (0.0, 1.0, None):
                problems.append(f"{label}: check {name} = {value!r} (not tri-state)")
    return problems


def write_run(results_dir: Path, run: dict) -> Path:
    problems = validate_run(run)
    if problems:
        raise ValueError(f"refusing to write invalid run: {problems}")
    runs_dir = results_dir / RUNS_DIRNAME
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run['run_id']}.json"
    path.write_text(
        json.dumps(run, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


def read_run(path: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_run(run)
    if problems:
        raise ValueError(f"{path}: invalid run record: {problems}")
    return run
