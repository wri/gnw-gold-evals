"""Generate the committed run index (results/index.json).

Like MANIFEST.json and COVERAGE.md, the index is derived and never
hand-edited: one entry per **committed** run file (enumerated via
``git ls-files``, so untracked local runs never leak in), carrying the
run's header fields and its ``buckets`` block verbatim. It exists so the
evals dashboard can list runs and render trends from a single fetch —
raw.githubusercontent.com cannot list directories. No rates are computed
here: scoring semantics stay in ``goldset.buckets`` / the consumers.

    uv run python tools/build_run_index.py            # writes results/index.json
    uv run python tools/build_run_index.py --check    # CI freshness gate

Benchmark runs (``results/benchmark/``) additionally carry their
``benchmark`` block and a ``canonical`` flag with ``canonical_reasons``: a
run is a North Star trend point only when it is prod, default profile (no
ff), 3 trials, and covers every active member of its manifest *as the
manifest stands now* (a member voided by a later erratum is not required).
The top-level ``benchmarks`` section lists each manifest under
``benchmarks/`` with its status and its runs, so the FE can draw the trend
from one fetch.

Output is deterministic (runs sorted by run_id, no timestamp), so the
freshness check is a plain byte compare. Regenerate and commit the index
together with every new run (see the after-run ritual in CLAUDE.md).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.benchmark import load_benchmark  # noqa: E402

SETS = ("gold", "challenge", "benchmark")
CANONICAL = {"environment": "prod", "ff": None, "num_trials": 3}

# Header fields projected verbatim when present; the optional ones
# (workers, trial_timeout, resumed, methodology_note) appear only on the
# runs that recorded them.
HEADER_FIELDS = (
    "started",
    "environment",
    "build",
    "ff",
    "harness",
    "judge_model",
    "num_trials",
    "workers",
    "trial_timeout",
    "resumed",
    "methodology_note",
    "caseset",
    "caseset_version",
)


def committed_run_paths(results_dir: Path, set_name: str) -> list[Path]:
    """Tracked run files for one set, via git (untracked runs excluded)."""
    root = results_dir.resolve().parent
    pathspec = f"{results_dir.name}/{set_name}/runs/*.json"
    proc = subprocess.run(
        ["git", "ls-files", "--", pathspec],
        cwd=root, capture_output=True, text=True, check=True,
    )
    return [root / line for line in proc.stdout.splitlines() if line.strip()]


def glob_run_paths(results_dir: Path, set_name: str) -> list[Path]:
    return sorted((results_dir / set_name / "runs").glob("*.json"))


def run_entry(path: Path, results_dir: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    run_id = run.get("run_id")
    if run_id != path.stem:
        raise SystemExit(
            f"{path}: run_id {run_id!r} does not match the filename — "
            "the ledger contract names files <run_id>.json"
        )
    rel = path.resolve().relative_to(results_dir.resolve().parent)
    entry: dict = {"run_id": run_id, "path": rel.as_posix()}
    entry.update({k: run[k] for k in HEADER_FIELDS if k in run})
    entry["buckets"] = run.get("buckets")
    if "benchmark" in run:
        entry["benchmark"] = run["benchmark"]
        reasons = canonical_reasons(run, results_dir.resolve().parent)
        entry["canonical"] = not reasons
        entry["canonical_reasons"] = reasons
    return entry


def canonical_reasons(run: dict, repo_root: Path) -> list[str]:
    """Why a benchmark run is not a trend point; empty means canonical."""
    reasons = [
        f"{field} is {run.get(field)!r}, canonical is {want!r}"
        for field, want in CANONICAL.items()
        if run.get(field) != want
    ]
    manifest = repo_root / run["benchmark"]["path"]
    if not manifest.exists():
        return reasons + [f"manifest {run['benchmark']['path']} not found"]
    active = load_benchmark(manifest).member_uids
    missing = active - {e.get("uid") for e in run.get("results", [])}
    if missing:
        reasons.append(f"{len(missing)} active member(s) not in the run")
    return reasons


def benchmark_versions(repo_root: Path, runs: list[dict]) -> dict:
    versions = {}
    for path in sorted((repo_root / "benchmarks").glob("*.json")):
        bench = load_benchmark(path)
        rel = path.relative_to(repo_root).as_posix()
        mine = [r for r in runs if r["benchmark"]["path"] == rel]
        versions[bench.version] = {
            "path": rel,
            "status": bench.status,
            "frozen": bench.frozen,
            "members": len(bench.active_members),
            "voided": len(bench.errata),
            "runs": [r["run_id"] for r in mine],
            "canonical_runs": [r["run_id"] for r in mine if r["canonical"]],
        }
    return versions


def build_index(results_dir: Path, use_glob: bool = False) -> dict:
    enumerate_paths = glob_run_paths if use_glob else committed_run_paths
    sets = {}
    for set_name in SETS:
        entries = [
            run_entry(path, results_dir)
            for path in enumerate_paths(results_dir, set_name)
        ]
        sets[set_name] = sorted(entries, key=lambda e: e["run_id"])
    return {
        "schema_version": 1,
        "generated_by": "tools/build_run_index.py",
        "sets": sets,
        "benchmarks": benchmark_versions(results_dir.resolve().parent,
                                         sets["benchmark"]),
    }


def render(results_dir: Path, use_glob: bool = False) -> str:
    index = build_index(results_dir, use_glob=use_glob)
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", type=Path, default=Path("results"))
    parser.add_argument("--out", type=Path, default=None,
                        help="default: <results-dir>/index.json")
    parser.add_argument("--glob", action="store_true",
                        help="enumerate runs from the filesystem instead of "
                             "git (tests over tmp trees)")
    parser.add_argument("--check", action="store_true",
                        help="verify the committed index is fresh; exit 1 if stale")
    args = parser.parse_args()

    out = args.out or (args.results_dir / "index.json")
    text = render(args.results_dir, use_glob=args.glob)
    if args.check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            print(f"{out} is stale — regenerate with: "
                  f"uv run python tools/build_run_index.py")
            return 1
        print(f"{out} is fresh")
        return 0
    out.write_text(text, encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
