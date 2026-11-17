"""The evaluation suites: which case store each reads and which ledger it fills.

    challenge  cases/challenge -> results/challenge  quality rates per set
    benchmark  cases/challenge -> results/benchmark  a manifest picks the cases
    gold       cases/v2        -> results/gold       legacy copy; GOLD itself
                                                     lives in project-zeno
                                                     evals/gold/

A run has no default suite. A run filed in the wrong ledger enters another
suite's trends, diffs and run index, so the harness refuses to guess and
refuses a store and a ledger that belong to different suites.

Paths are relative to the working directory (the repo root), as every other
default in the harness is. A store or ledger is recognised by its last two
path parts, so an absolute path to the same directory is recognised too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from goldset.ledger import PARTIAL_SUFFIX, RUNS_DIRNAME


@dataclass(frozen=True)
class Suite:
    name: str
    cases_dir: Path
    results_dir: Path
    # The canonical CHALLENGE series holds back `todo` rows, whose
    # expectations are not pinned yet (cases/challenge/README.md). A BENCHMARK
    # run ignores status: the manifest names its members.
    status_exclude: str


SUITES: dict[str, Suite] = {
    "challenge": Suite("challenge", Path("cases/challenge"),
                       Path("results/challenge"), "not doing,todo"),
    "benchmark": Suite("benchmark", Path("cases/challenge"),
                       Path("results/benchmark"), "not doing"),
    "gold": Suite("gold", Path("cases/v2"), Path("results/gold"), "not doing"),
}
SUITE_NAMES = tuple(SUITES)
# For a store outside the known suites, run with explicit dirs.
DEFAULT_STATUS_EXCLUDE = "not doing"

SUITES_HELP = (
    "--suite challenge (cases/challenge -> results/challenge), "
    "--benchmark MANIFEST (benchmarks/<version>.json -> results/benchmark), "
    "or --suite gold (cases/v2 -> results/gold, the legacy GOLD copy)"
)


class SuiteError(ValueError):
    """No suite chosen, or dirs that would file a run in the wrong ledger."""


def _tail(path: Path) -> tuple[str, ...]:
    return Path(path).resolve().parts[-2:]


def store_suite(cases_dir: Path) -> str | None:
    """The suite whose case store this is ('challenge' or 'gold'), else None.
    cases/challenge answers 'challenge': BENCHMARK borrows that store."""
    tail = _tail(cases_dir)
    return next((s.name for s in SUITES.values() if s.cases_dir.parts == tail), None)


def ledger_suite(results_dir: Path) -> str | None:
    """The suite whose results ledger this is, else None."""
    tail = _tail(results_dir)
    return next((s.name for s in SUITES.values() if s.results_dir.parts == tail), None)


@dataclass(frozen=True)
class RunDirs:
    suite: str | None  # None: a store outside the suites, run with explicit dirs
    cases_dir: Path
    results_dir: Path

    @property
    def status_exclude(self) -> str:
        if self.suite is None:
            return DEFAULT_STATUS_EXCLUDE
        return SUITES[self.suite].status_exclude


def _check_suite_name(suite: str | None) -> None:
    if suite is not None and suite not in SUITES:
        raise SuiteError(f"unknown suite {suite!r}; choose one of {', '.join(SUITE_NAMES)}")


def resolve_run_dirs(*, suite: str | None, manifest_cases_dir: Path | None,
                     cases_dir: Path | None, results_dir: Path | None) -> RunDirs:
    """Where a fresh run reads its cases and files its record.

    ``manifest_cases_dir`` is the --benchmark manifest's source store, None
    without --benchmark. An explicit ``cases_dir`` or ``results_dir`` wins
    over the suite's own. Raises SuiteError when nothing names a suite, or
    when the store and the ledger belong to different suites.
    """
    _check_suite_name(suite)
    if manifest_cases_dir is not None:
        if suite not in (None, "benchmark"):
            raise SuiteError(f"--benchmark runs the benchmark suite; drop --suite {suite}")
        if cases_dir is not None and Path(cases_dir).resolve() != Path(
                manifest_cases_dir).resolve():
            raise SuiteError(
                f"--cases-dir {cases_dir} is not the manifest's source store "
                f"{manifest_cases_dir}; drop --cases-dir")
        suite, cases_dir = "benchmark", Path(manifest_cases_dir)
    elif suite == "benchmark":
        raise SuiteError("--suite benchmark needs --benchmark MANIFEST "
                         "(benchmarks/<version>.json): a BENCHMARK run is "
                         "exactly a manifest's members")
    elif suite is not None:
        cases_dir = Path(cases_dir) if cases_dir is not None else SUITES[suite].cases_dir
    elif cases_dir is not None:
        cases_dir = Path(cases_dir)
        suite = store_suite(cases_dir)
        if suite is None and results_dir is None:
            raise SuiteError(f"{cases_dir} is not a known case store, so its "
                             "ledger cannot be inferred; pass --results-dir")
    else:
        raise SuiteError(f"choose what to run: {SUITES_HELP}; or pass "
                         "--cases-dir (with --results-dir for another store)")
    results_dir = Path(results_dir) if results_dir is not None else SUITES[suite].results_dir
    _refuse_mismatch(cases_dir, results_dir, benchmark=manifest_cases_dir is not None)
    return RunDirs(suite, cases_dir, results_dir)


def _refuse_mismatch(cases_dir: Path, results_dir: Path, *, benchmark: bool) -> None:
    ledger = ledger_suite(results_dir)
    if benchmark:
        if ledger not in (None, "benchmark"):
            raise SuiteError(f"a --benchmark run is filed in "
                             f"{SUITES['benchmark'].results_dir}, not {results_dir}")
        return
    if ledger == "benchmark":
        raise SuiteError(f"{results_dir} is the BENCHMARK ledger; only a "
                         "--benchmark MANIFEST run is filed there")
    store = store_suite(cases_dir)
    if store and ledger and store != ledger:
        raise SuiteError(
            f"{cases_dir} is the {store} store but {results_dir} is the {ledger} "
            f"ledger; a run is filed with its own suite (--suite {store})")


def resolve_results_dir(suite: str | None, results_dir: Path | None) -> Path:
    """A ledger named by --results-dir or --suite (prune-artifacts)."""
    _check_suite_name(suite)
    if results_dir is not None:
        return Path(results_dir)
    if suite is not None:
        return SUITES[suite].results_dir
    raise SuiteError(f"choose a ledger: --suite {{{','.join(SUITE_NAMES)}}} "
                     "or --results-dir")


def locate_resume_dir(run_id: str, *, suite: str | None,
                      results_dir: Path | None) -> Path:
    """The ledger that holds run ``run_id``, for --resume.

    The partial's header does not record its ledger, so an explicit
    --results-dir or --suite says where to look. Without either, every known
    ledger is searched for the run (its partial, or its record if it was
    already finalised) and only a single match is used.
    """
    if results_dir is not None or suite is not None:
        return resolve_results_dir(suite, results_dir)
    looked = [s.results_dir / RUNS_DIRNAME for s in SUITES.values()]
    found = [
        runs.parent for runs in looked
        if (runs / f"{run_id}{PARTIAL_SUFFIX}").exists()
        or (runs / f"{run_id}.json").exists()
    ]
    if len(found) == 1:
        return found[0]
    if not found:
        raise SuiteError(f"run {run_id} is in none of "
                         f"{', '.join(map(str, looked))}; pass --results-dir")
    raise SuiteError(f"run {run_id} is in more than one ledger "
                     f"({', '.join(map(str, found))}); pass --suite or --results-dir")


def cases_dir_for(run: dict, *, cases_dir: Path | None = None,
                  suite: str | None = None) -> Path:
    """The case store a tool reads alongside one ledger run: --cases-dir, else
    the --suite's store, else the store the run records it measured."""
    _check_suite_name(suite)
    if cases_dir is not None:
        return Path(cases_dir)
    if suite is not None:
        return SUITES[suite].cases_dir
    run_id = run.get("run_id", "?")
    caseset = run.get("caseset")
    if not caseset:
        raise SuiteError(f"run {run_id} does not record its case store (runs "
                         "before 2026-08-04 lack caseset); pass --cases-dir or --suite")
    recorded = Path("cases") / caseset
    if not recorded.is_dir():
        raise SuiteError(f"run {run_id} measured the store {caseset!r}, but "
                         f"{recorded} does not exist here; pass --cases-dir")
    return recorded
