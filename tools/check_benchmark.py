"""Verify every BENCHMARK manifest against its source store (CI gate).

    uv run python tools/check_benchmark.py                 # all benchmarks/*.json
    uv run python tools/check_benchmark.py benchmarks/2026.json

For each manifest: structural validation (``goldset.benchmark``), then per
active (non-voided) member: the uid exists in the source store, the case is
``ready``, and the frozen facets (id, set, cohort, difficulty, stages) still
match the live case. Every member's language must match its case's, so an
English version cannot hold a case in another language. A member with a
``language`` or a ``twin_uid`` is also checked as half of a pair: its case has that language, the case's ``twin``
is the case ``twin_uid`` names, and that twin is an active member of this
version or of the ``pairs_with`` version. A problem is an **error** on a
frozen version (exit 1) and a **warning** on a draft: editing a CHALLENGE
case that a draft sampled is allowed, but it must be visible, because it
silently shrinks the draft.
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
from goldset.store import Case, load_store  # noqa: E402


def pair_problems(
    bench: Benchmark, by_uid: dict[str, Case], manifests_dir: Path
) -> list[str]:
    """Problems with the language pairs. A member whose uid is not in the
    store is skipped: the caller reports it."""
    problems = []
    twin_members = set(bench.member_uids)
    # Without the paired version, membership there cannot be judged.
    paired_version_read = True
    if bench.pairs_with:
        other = manifests_dir / f"{bench.pairs_with}.json"
        try:
            twin_members |= load_benchmark(other).member_uids
        except FileNotFoundError:
            paired_version_read = False
            problems.append(f"pairs_with {bench.pairs_with!r}: {other} does not exist")
        except ValueError as exc:
            paired_version_read = False
            problems.append(f"pairs_with {bench.pairs_with!r}: {exc}")
    by_id = {case.id: case for case in by_uid.values()}
    for m in bench.active_members:
        case = by_uid.get(m.uid)
        if case is None:
            continue
        label = f"{m.id} ({m.uid})"
        if case.language != (m.language or "en"):
            problems.append(
                f"{label}: language {m.language or 'en'!r} differs from the "
                f"case's {case.language!r}"
            )
        if not (m.language or m.twin_uid):
            continue
        if m.language:
            twin = by_id.get(case.twin)
            if twin is None or twin.uid != m.twin_uid:
                problems.append(
                    f"{label}: twin_uid {m.twin_uid} is not the uid of the "
                    f"case's twin {case.twin!r}"
                )
        else:
            # An English member names the case in another language instead.
            native = by_uid.get(m.twin_uid)
            if native is None or native.twin != case.id:
                problems.append(
                    f"{label}: twin_uid {m.twin_uid} is not a case that names "
                    f"{case.id} as its twin"
                )
        if m.twin_uid not in twin_members and paired_version_read:
            where = "this version"
            if bench.pairs_with:
                where += f" or of {bench.pairs_with}"
            problems.append(
                f"{label}: twin_uid {m.twin_uid} is not an active member of {where}"
            )
    return problems


def member_problems(
    bench: Benchmark, repo_root: Path, manifests_dir: Path
) -> list[str]:
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
    return problems + pair_problems(bench, by_uid, manifests_dir)


def check(path: Path, repo_root: Path) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one manifest."""
    try:
        bench = load_benchmark(path)
    except ValueError as exc:
        return [str(exc)], []
    if bench.status == "retired":
        return [], []
    problems = [
        f"{path.name}: {p}" for p in member_problems(bench, repo_root, path.parent)
    ]
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
