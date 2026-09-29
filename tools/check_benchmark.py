"""Verify every BENCHMARK manifest against its source store (CI gate).

    uv run python tools/check_benchmark.py                 # all benchmarks/*.json
    uv run python tools/check_benchmark.py benchmarks/2026.json

For each manifest: structural validation (``goldset.benchmark``), then per
active (non-voided) member: the uid exists in the source store, the case is
``ready``, and the frozen facets (id, set, cohort, difficulty, stages) still
match the live case. A problem is an **error** on a frozen version (exit 1)
and a **warning** on a draft: editing a CHALLENGE case that a draft sampled
is allowed, but it must be visible, because it silently shrinks the draft.
Retired versions are validated structurally only.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from benchmark_sample import stages_for  # noqa: E402

from goldset.benchmark import Benchmark, load_benchmark  # noqa: E402
from goldset.store import load_store  # noqa: E402


def member_problems(bench: Benchmark, repo_root: Path) -> list[str]:
    cases_dir = repo_root / bench.source.get("cases_dir", "cases/challenge")
    by_uid = {uid: case for _p, case, uid in load_store(cases_dir)}
    problems = []
    for m in bench.active_members:
        case = by_uid.get(m.uid)
        if case is None:
            problems.append(f"{m.id} ({m.uid}): uid not in {cases_dir} — "
                            "the case was edited or deleted; void it with an erratum")
            continue
        if case.status != "ready":
            problems.append(f"{m.id} ({m.uid}): status {case.status!r}, not ready")
        live = {"id": case.id, "set": case.set, "cohort": case.group,
                "difficulty": case.notes.get("difficulty", ""),
                "stages": tuple(stages_for(case))}
        frozen = {"id": m.id, "set": m.set, "cohort": m.cohort,
                  "difficulty": m.difficulty, "stages": m.stages}
        drift = [k for k in live if live[k] != frozen[k]]
        if drift:
            problems.append(f"{m.id} ({m.uid}): frozen {drift} differ from the live case")
    return problems


def check(path: Path, repo_root: Path) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one manifest."""
    try:
        bench = load_benchmark(path)
    except ValueError as exc:
        return [str(exc)], []
    if bench.status == "retired":
        return [], []
    problems = [f"{path.name}: {p}" for p in member_problems(bench, repo_root)]
    return (problems, []) if bench.status == "frozen" else ([], problems)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifests", nargs="*", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()
    paths = args.manifests or sorted((args.repo_root / "benchmarks").glob("*.json"))
    failed = False
    for path in paths:
        errors, warnings = check(path, args.repo_root)
        for w in warnings:
            print(f"warning: {w}")
        for e in errors:
            print(f"error: {e}")
        failed |= bool(errors)
        if not errors:
            print(f"ok: {path}" + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
