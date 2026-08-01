"""Flakiness table from a multi-trial run (PR-08 steps 2, 3, 5).

    uv run python tools/flakiness.py results/runs/<trials-run>.json

Per check: mean, std (population), and flip count across trials — the
admission evidence for judged checks (std <= 0.10 over 3 trials, PLAN §4)
and the guard-validation evidence (deterministic checks at std <= 0.04).
Per case: which rows flapped at all, so the multiturn seed table for
PR-07's spec falls straight out of `--per-case`.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import base_check_name, is_info_only
from goldset.ledger import read_run
from goldset.registry import EVALUATORS

JUDGED_KINDS = {"llm_judge", "mixed"}
JUDGED_CHECKS = frozenset(
    field.removesuffix("_score")
    for spec in EVALUATORS
    if spec.kind in JUDGED_KINDS
    for field in spec.score_fields
)

DETERMINISTIC_STD_GATE = 0.04
JUDGED_STD_GATE = 0.10


def trial_values(entry: dict, check: str) -> list[float | None]:
    trials = entry.get("trials")
    if not trials:
        return [entry["checks"].get(check)]
    return [t["checks"].get(check) for t in trials]


def collect(run: dict) -> tuple[dict, list[dict]]:
    """(per-check stats, per-case flap list)."""
    per_check: dict[str, list[float]] = {}
    flappy_cases: list[dict] = []
    for entry in run["results"]:
        if entry.get("stale_case"):
            continue
        flapped: list[str] = []
        for check in entry.get("checks", {}):
            values = [v for v in trial_values(entry, check) if v is not None]
            if not values:
                continue
            per_check.setdefault(base_check_name(check), []).extend(values)
            if len(set(values)) > 1:
                flapped.append(check)
        if flapped:
            flappy_cases.append({"id": entry.get("id"), "checks": sorted(flapped)})

    stats: dict[str, dict] = {}
    for check, values in sorted(per_check.items()):
        std = statistics.pstdev(values) if len(values) > 1 else 0.0
        gate = JUDGED_STD_GATE if check in JUDGED_CHECKS else DETERMINISTIC_STD_GATE
        stats[check] = {
            "n": len(values),
            "mean": statistics.mean(values),
            "std": std,
            "kind": "judged" if check in JUDGED_CHECKS else "deterministic",
            "info_only": is_info_only(check),
            "within_gate": std <= gate,
        }
    return stats, flappy_cases


def render(run: dict, stats: dict, flappy: list[dict], per_case: bool) -> str:
    lines = [
        f"# Flakiness: {run['run_id']} ({run['num_trials']} trials)",
        "",
        "| check | kind | n | mean | std | gate |",
        "|---|---|---:|---:|---:|---|",
    ]
    for check, row in stats.items():
        flag = "info-only" if row["info_only"] else (
            "ok" if row["within_gate"] else "**OVER GATE**"
        )
        lines.append(
            f"| {check} | {row['kind']} | {row['n']} | {row['mean']:.2f} "
            f"| ±{row['std']:.2f} | {flag} |"
        )
    over = [c for c, r in stats.items() if not r["within_gate"] and not r["info_only"]]
    lines += [
        "",
        f"Checks over their std gate: {', '.join(over) if over else 'none'}. "
        f"Rows that flapped at all: {len(flappy)}.",
    ]
    if per_case and flappy:
        lines += ["", "## Flapping rows", ""]
        lines += [f"- {c['id']}: {', '.join(c['checks'])}" for c in flappy]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--per-case", action="store_true")
    args = parser.parse_args()
    run = read_run(args.run)
    if run.get("num_trials", 1) < 2:
        print("warning: single-trial run — stds are vacuous\n")
    stats, flappy = collect(run)
    print(render(run, stats, flappy, args.per_case))
    over = [c for c, r in stats.items() if not r["within_gate"] and not r["info_only"]]
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
