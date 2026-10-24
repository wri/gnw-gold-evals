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
A benchmark run whose page data is committed
(``results/benchmark/pages/<run_id>.json``, ``tools/benchmark_page.py``)
also carries its ``page`` path. When that page combines the run with an
earlier base run (a rerun of revised members, ``benchmark_page.py --base``),
the entry carries ``composed_with`` (the base run ids) and is judged
canonical over the runs together: each must be prod, default profile and 3
trials, and between them they must cover every active member. The top-level ``benchmarks`` section lists each manifest under
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


def committed_page_paths(results_dir: Path) -> set[str]:
    """Tracked benchmark page files, as repo-relative paths."""
    proc = subprocess.run(
        ["git", "ls-files", "--", f"{results_dir.name}/benchmark/pages/*.json"],
        cwd=results_dir.resolve().parent, capture_output=True, text=True, check=True,
    )
    return {line for line in proc.stdout.splitlines() if line.strip()}


def glob_page_paths(results_dir: Path) -> set[str]:
    root = results_dir.resolve().parent
    return {p.resolve().relative_to(root).as_posix()
            for p in (results_dir / "benchmark" / "pages").glob("*.json")}


def load_run(path: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    if run.get("run_id") != path.stem:
        raise SystemExit(
            f"{path}: run_id {run.get('run_id')!r} does not match the filename — "
            "the ledger contract names files <run_id>.json"
        )
    return run


def run_entry(path: Path, results_dir: Path, pages: frozenset[str] = frozenset(),
              runs_by_id: dict[str, dict] | None = None) -> dict:
    run = load_run(path)
    run_id = run["run_id"]
    rel = path.resolve().relative_to(results_dir.resolve().parent)
    entry: dict = {"run_id": run_id, "path": rel.as_posix()}
    entry.update({k: run[k] for k in HEADER_FIELDS if k in run})
    entry["buckets"] = run.get("buckets")
    if "benchmark" in run:
        entry["benchmark"] = run["benchmark"]
        page = f"{results_dir.name}/benchmark/pages/{run_id}.json"
        base_ids = page_bases(results_dir.resolve().parent / page, run_id) if page in pages else []
        if base_ids:
            entry["composed_with"] = base_ids
        reasons = canonical_reasons(run, results_dir.resolve().parent,
                                    base_ids, runs_by_id or {})
        entry["canonical"] = not reasons
        entry["canonical_reasons"] = reasons
        if page in pages:
            entry["page"] = page
    return entry


def page_bases(page_path: Path, run_id: str) -> list[str]:
    """The base runs a combined page draws on (its ``run.sources`` other
    than the run itself); empty for a single-run page."""
    sources = json.loads(page_path.read_text(encoding="utf-8"))["run"].get("sources") or []
    return [s["run_id"] for s in sources if s["run_id"] != run_id]


def canonical_reasons(run: dict, repo_root: Path, base_ids: list[str] = (),
                      runs_by_id: dict[str, dict] | None = None) -> list[str]:
    """Why a benchmark run (with the base runs its page combines it with)
    is not a trend point; empty means canonical."""
    runs_by_id = runs_by_id or {}
    reasons = [
        f"{field} is {run.get(field)!r}, canonical is {want!r}"
        for field, want in CANONICAL.items()
        if run.get(field) != want
    ]
    measured = {e.get("uid") for e in run.get("results", [])}
    for base_id in base_ids:
        base = runs_by_id.get(base_id)
        if base is None:
            reasons.append(f"base run {base_id} is not committed")
            continue
        reasons += [
            f"base {base_id}: {field} is {base.get(field)!r}, canonical is {want!r}"
            for field, want in CANONICAL.items()
            if base.get(field) != want
        ]
        measured |= {e.get("uid") for e in base.get("results", [])}
    manifest = repo_root / run["benchmark"]["path"]
    if not manifest.exists():
        return reasons + [f"manifest {run['benchmark']['path']} not found"]
    missing = load_benchmark(manifest).member_uids - measured
    if missing:
        where = "the run and its base" if base_ids else "the run"
        reasons.append(f"{len(missing)} active member(s) not in {where}")
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
    pages = frozenset(glob_page_paths(results_dir) if use_glob else committed_page_paths(results_dir))
    sets = {}
    for set_name in SETS:
        paths = enumerate_paths(results_dir, set_name)
        # A combined benchmark page's base is another committed run of the set.
        runs_by_id = ({p.stem: load_run(p) for p in paths}
                      if set_name == "benchmark" else {})
        entries = [
            run_entry(path, results_dir, pages, runs_by_id)
            for path in paths
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
