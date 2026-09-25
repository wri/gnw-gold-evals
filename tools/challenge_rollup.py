"""Roll up CHALLENGE run(s) into published quality rates.

Usage::

    uv run python tools/challenge_rollup.py results/challenge/runs/<run>.json
    uv run python tools/challenge_rollup.py <run1>.json <run2>.json \
        --cases-dir cases/challenge --json scratch/rollup.json

Where GOLD's verdict is a regression count (``tools/diff_runs.py``), a
CHALLENGE run's verdict is a **pass rate per cohort** with a confidence
interval, compared against ``cases/challenge/TARGETS.yml``. Semantics:

- The **rate** is the majority-verdict pass rate: rows whose non-info
  checks all passed (``goldset.buckets.row_verdict``), over rows that were
  actually measured (verdict ``pass`` or ``fail``).
- **strict** additionally requires every trial of every non-info check to
  have passed — the "clean on every trial" rate. On 1-trial runs it equals
  the rate.
- **Errors are availability, not quality**: errored rows leave the
  denominator entirely and are reported as an availability figure, so
  infrastructure flakiness never contaminates the published rate.
- ``uncovered`` rows (nothing evaluated) and ``stale`` rows (uid no longer
  in the store) are reported, never counted.
- **Latency** (median, p90 nearest rank, mean) is reported overall, per set
  and per cohort over every trial of the measured rows (pass or fail);
  errored rows are excluded, since a timeout measures availability, not
  speed. Basis: ``stream_s`` (POST /api/chat to the last stream line, the
  agent turn) where the run recorded it, else ``latency_s`` (which also
  spans the state GET); judge time is in neither. Passing two or more runs
  adds a side-by-side latency table with median deltas against the first
  run, flagged as not comparable when env, workers or basis differ. For a
  latency comparison run both sides with ``--workers 1``.
- Confidence intervals are Wilson 95%; a published "70%" from 12 cases must
  say how soft it is.

The hierarchy is **set → cohort → case**: set = ``case.set`` (the level new
CHALLENGE sets are added at — ``aoi`` first; rows without one group under
``unset``), cohort = ``case.group``, difficulty = ``notes.difficulty``
(unlabelled rows group under ``unlabelled``). Rates are rolled up overall,
per set, and per cohort/difficulty within each set; ``TARGETS.yml`` scopes
cohort targets per set. Passing several runs renders one section per run
plus a cross-run rate table over overall + per-set rates (comparable runs
only — same env, ff, trials, caseset_version; the tool warns, but does not
refuse, on a mix).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import is_info_only, row_verdict  # noqa: E402
from goldset.store import load_store  # noqa: E402

Z_95 = 1.96


def wilson(passed: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; (0.0, 1.0) when n=0."""
    if n == 0:
        return (0.0, 1.0)
    p = passed / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def _trial_list(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-trial detail as a list. The ledger writes ``trials`` as a list
    (``cli.merge_trials``); older fixtures used a dict keyed by trial, so
    both shapes are accepted."""
    trials = entry.get("trials") or []
    if isinstance(trials, dict):
        trials = list(trials.values())
    return [t for t in trials if isinstance(t, dict)]


def _basis(r: dict[str, Any]) -> str:
    basis = r.get("latency_basis") or {}
    return ", ".join(f"{k} x{v}" for k, v in basis.items()) or "none"


def latency_comparison(rollups: list[dict[str, Any]]) -> list[str]:
    """Side-by-side latency (median / p90 / mean seconds) per run for the
    overall row, each set and each cohort, plus the median delta of every
    later run against the first. Loudly flags pairs that are not comparable:
    differing env or workers, or a different latency basis."""
    lines = ["## Cross-run latency (seconds: median / p90 / mean; errors excluded)"]
    envs = {r["environment"] for r in rollups}
    workers = {r.get("workers") for r in rollups}
    bases = {tuple(sorted((r.get("latency_basis") or {}).keys())) for r in rollups}
    problems = []
    if len(envs) > 1:
        problems.append(f"env differs ({', '.join(sorted(map(str, envs)))}): "
                        "network and infrastructure differ, so the gap is not the agent")
    if len(workers) > 1:
        problems.append(f"workers differ ({', '.join(sorted(map(str, workers)))}): "
                        "concurrency changes contention")
    if len(bases) > 1:
        problems.append("latency basis differs (stream_s vs latency_s)")
    for problem in problems:
        lines.append(f"WARNING: latency NOT comparable - {problem}.")
    base = rollups[0]
    header = "| scope | " + " | ".join(r["run_id"] for r in rollups)
    header += "".join(f" | d median vs {base['run_id']}" for _ in rollups[1:]) + " |"
    lines.append(header)
    lines.append("|---" * (1 + len(rollups) + len(rollups) - 1) + "|")

    def cell(stat):
        if not stat or stat.get("latency_median_s") is None:
            return "-"
        return (f"{_secs(stat['latency_median_s'])} / {_secs(stat['latency_p90_s'])}"
                f" / {_secs(stat['latency_mean_s'])}")

    def delta(stat, base_stat):
        if not stat or not base_stat or None in (
            stat.get("latency_median_s"), base_stat.get("latency_median_s")
        ):
            return "-"
        return f"{stat['latency_median_s'] - base_stat['latency_median_s']:+.1f}"

    scopes: list[tuple[str, Any]] = [("overall", lambda r: r["overall"])]
    for set_name in sorted({s for r in rollups for s in r["by_set"]}):
        scopes.append((set_name, lambda r, s=set_name: r["by_set"].get(s)))
        groups = sorted({g for r in rollups for g in (r["by_set"].get(set_name) or {}).get("by_group", {})})
        for group in groups:
            scopes.append((
                f"{set_name} / {group}",
                lambda r, s=set_name, g=group: (r["by_set"].get(s) or {}).get("by_group", {}).get(g),
            ))
    for label, get in scopes:
        row = [label] + [cell(get(r)) for r in rollups]
        row += [delta(get(r), get(base)) for r in rollups[1:]]
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return lines


def _secs(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}"


def strict_clean(entry: dict[str, Any]) -> bool:
    """True when the row passed AND no trial shows a failing non-info check.

    Rows without per-trial data (1-trial runs) fall back to the majority
    verdict.
    """
    if row_verdict(entry) != "pass":
        return False
    for trial in _trial_list(entry):
        for name, value in (trial.get("checks") or {}).items():
            if not is_info_only(name) and value == 0.0:
                return False
    return True


def _new_stat() -> dict[str, Any]:
    return {"n": 0, "passed": 0, "strict_passed": 0, "_latencies": []}


def _one_latency(record: dict[str, Any]) -> tuple[float | None, str | None]:
    """``stream_s`` (POST to end of stream: the agent turn) when recorded,
    else ``latency_s`` (also spans the harness's state GET); neither ever
    includes judge time."""
    for key in ("stream_s", "latency_s"):
        value = record.get(key)
        if isinstance(value, (int, float)):
            return float(value), key
    return None, None


def entry_latencies(entry: dict[str, Any]) -> list[tuple[float, str]]:
    """Every trial's latency for a row as (seconds, basis): per trial on
    multi-trial entries, else the entry's own."""
    records = _trial_list(entry) or [entry]
    out = []
    for record in records:
        value, basis = _one_latency(record)
        if value is not None:
            out.append((value, basis))
    return out


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100); None on no data."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def _finish(stat: dict[str, Any]) -> dict[str, Any]:
    latencies = stat.pop("_latencies", [])
    stat["latency_n"] = len(latencies)
    stat["latency_median_s"] = percentile(latencies, 50)
    stat["latency_p90_s"] = percentile(latencies, 90)
    stat["latency_mean_s"] = sum(latencies) / len(latencies) if latencies else None
    n, passed = stat["n"], stat["passed"]
    lo, hi = wilson(passed, n)
    stat["rate"] = passed / n if n else None
    stat["ci_low"], stat["ci_high"] = lo, hi
    stat["strict_rate"] = stat["strict_passed"] / n if n else None
    return stat


def rollup_run(run: dict[str, Any], cases_by_uid: dict[str, Any]) -> dict[str, Any]:
    """Compute the rate block for one run against the current store."""
    verdicts = {"pass": 0, "fail": 0, "error": 0, "uncovered": 0}
    stale: list[str] = []
    errored: list[dict[str, str]] = []
    uncovered: list[str] = []
    overall = _new_stat()
    sets: dict[str, dict] = defaultdict(
        lambda: {
            "stat": _new_stat(),
            "by_group": defaultdict(_new_stat),
            "by_difficulty": defaultdict(_new_stat),
        }
    )
    failing: list[dict[str, str]] = []
    latency_basis: Counter = Counter()

    measured_uids: set[str] = set()
    for entry in run.get("results", []):
        uid = entry.get("uid", "")
        case = cases_by_uid.get(uid)
        if case is None or entry.get("stale_case"):
            stale.append(entry.get("id", uid))
            continue
        measured_uids.add(uid)
        verdict = row_verdict(entry)
        verdicts[verdict] += 1
        if verdict == "error":
            errored.append({"id": case.id, "error": str(entry.get("error") or "judge_errors")})
            continue
        if verdict == "uncovered":
            uncovered.append(case.id)
            continue
        case_set = case.set or "unset"
        difficulty = case.notes.get("difficulty", "unlabelled")
        passed = verdict == "pass"
        strict = strict_clean(entry)
        latencies = entry_latencies(entry)
        bucket = sets[case_set]
        for stat in (
            overall,
            bucket["stat"],
            bucket["by_group"][case.group],
            bucket["by_difficulty"][difficulty],
        ):
            stat["n"] += 1
            stat["passed"] += passed
            stat["strict_passed"] += strict
            stat["_latencies"].extend(value for value, _basis in latencies)
        latency_basis.update(basis for _value, basis in latencies)
        if not passed:
            failing.append(
                {
                    "id": case.id,
                    "set": case_set,
                    "group": case.group,
                    "difficulty": difficulty,
                    "failed_checks": ", ".join(
                        sorted(
                            name
                            for name, value in entry.get("checks", {}).items()
                            if value == 0.0 and not is_info_only(name)
                        )
                    ),
                }
            )

    active_not_run = sorted(
        case.id
        for uid, case in cases_by_uid.items()
        if uid not in measured_uids and case.status.lower() != "not doing"
    )
    total = len(run.get("results", []))
    non_stale = total - len(stale)
    return {
        "run_id": run.get("run_id"),
        "build": run.get("build"),
        "environment": run.get("environment"),
        "ff": run.get("ff") or "default",
        "num_trials": run.get("num_trials"),
        "workers": run.get("workers"),
        "latency_basis": dict(sorted(latency_basis.items())),
        "caseset": run.get("caseset"),
        "caseset_version": run.get("caseset_version"),
        "rows_total": total,
        "verdicts": verdicts,
        "availability": (
            (non_stale - verdicts["error"]) / non_stale if non_stale else None
        ),
        "stale": sorted(stale),
        "errored": sorted(errored, key=lambda e: e["id"]),
        "uncovered": sorted(uncovered),
        "not_run": active_not_run,
        "overall": _finish(overall),
        "by_set": {
            name: {
                **_finish(bucket["stat"]),
                "by_group": {
                    k: _finish(v) for k, v in sorted(bucket["by_group"].items())
                },
                "by_difficulty": {
                    k: _finish(v) for k, v in sorted(bucket["by_difficulty"].items())
                },
            }
            for name, bucket in sorted(sets.items())
        },
        "failing": sorted(failing, key=lambda f: f["id"]),
    }


def load_targets(path: Path) -> dict[str, Any]:
    """Targets keyed set -> {overall, targets: {cohort: rate}}, plus a
    challenge-wide overall."""
    if not path.exists():
        return {"sets": {}, "overall": None, "meta": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sets = {
        name: {
            "overall": block.get("overall"),
            "targets": block.get("targets") or {},
        }
        for name, block in (data.get("sets") or {}).items()
    }
    return {
        "sets": sets,
        "overall": data.get("overall"),
        "meta": data.get("meta") or {},
    }


def _pct(value: float | None) -> str:
    return "-" if value is None else f"{100 * value:.1f}%"


def _ci(stat: dict[str, Any]) -> str:
    if not stat["n"]:
        return "-"
    return f"{100 * stat['ci_low']:.1f}-{100 * stat['ci_high']:.1f}%"


def _target_cell(rate: float | None, target: float | None) -> str:
    if target is None:
        return "-"
    if rate is None:
        return f"{100 * target:.0f}% / not measured"
    delta = 100 * (rate - target)
    status = "MET" if rate >= target else "BELOW"
    return f"{100 * target:.0f}% / {status} ({delta:+.1f} pts)"


def render_markdown(rollups: list[dict[str, Any]], targets: dict[str, Any]) -> str:
    lines: list[str] = []
    for r in rollups:
        v = r["verdicts"]
        lines.append(f"# CHALLENGE rollup - {r['run_id']}")
        lines.append(
            f"build {r['build']} | env {r['environment']} | ff {r['ff']} | "
            f"trials {r['num_trials']} | caseset {r['caseset']} "
            f"({r['caseset_version']})"
        )
        lines.append("")
        lines.append(
            f"Rows {r['rows_total']} | measured {v['pass'] + v['fail']} | "
            f"errors {v['error']} (availability {_pct(r['availability'])}) | "
            f"uncovered {v['uncovered']} | stale {len(r['stale'])} | "
            f"not run {len(r['not_run'])}"
        )
        lines.append("")
        o = r["overall"]
        lines.append("## Overall")
        lines.append(
            f"pass rate **{_pct(o['rate'])}** ({o['passed']}/{o['n']}, "
            f"95% CI {_ci(o)}) | strict (all trials clean) "
            f"{_pct(o['strict_rate'])}"
        )
        lines.append(
            f"latency (s, excl. errors): median {_secs(o['latency_median_s'])} | "
            f"p90 {_secs(o['latency_p90_s'])} | mean {_secs(o['latency_mean_s'])} | "
            f"n {o['latency_n']} trials | basis {_basis(r)} | workers {r.get('workers')}"
        )
        overall_target = targets.get("overall")
        if overall_target is not None:
            lines.append(f"target: {_target_cell(o['rate'], overall_target)}")
        set_targets = targets.get("sets", {})
        for set_name, s in r["by_set"].items():
            st = set_targets.get(set_name, {})
            lines.append("")
            lines.append(f"## Set: {set_name}")
            lines.append(
                f"pass rate **{_pct(s['rate'])}** ({s['passed']}/{s['n']}, "
                f"95% CI {_ci(s)}) | strict {_pct(s['strict_rate'])} | "
                f"latency median {_secs(s['latency_median_s'])}, "
                f"p90 {_secs(s['latency_p90_s'])}, mean {_secs(s['latency_mean_s'])}"
            )
            if st.get("overall") is not None:
                lines.append(f"target: {_target_cell(s['rate'], st['overall'])}")
            lines.append("")
            lines.append("### By cohort")
            lines.append(
                "| cohort | n | passed | rate | 95% CI | strict | target "
                "| median s | p90 s | mean s |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|---|")
            group_targets = st.get("targets", {})
            for group, stat in s["by_group"].items():
                lines.append(
                    f"| {group} | {stat['n']} | {stat['passed']} | "
                    f"{_pct(stat['rate'])} | {_ci(stat)} | {_pct(stat['strict_rate'])} "
                    f"| {_target_cell(stat['rate'], group_targets.get(group))} "
                    f"| {_secs(stat['latency_median_s'])} "
                    f"| {_secs(stat['latency_p90_s'])} "
                    f"| {_secs(stat['latency_mean_s'])} |"
                )
            lines.append("")
            lines.append("### By difficulty")
            lines.append("| difficulty | n | passed | rate | 95% CI | strict |")
            lines.append("|---|---|---|---|---|---|")
            for difficulty, stat in s["by_difficulty"].items():
                lines.append(
                    f"| {difficulty} | {stat['n']} | {stat['passed']} | "
                    f"{_pct(stat['rate'])} | {_ci(stat)} | "
                    f"{_pct(stat['strict_rate'])} |"
                )
        if r["failing"]:
            lines.append("")
            lines.append("## Failing rows")
            lines.append("| id | set | cohort | difficulty | failed checks |")
            lines.append("|---|---|---|---|---|")
            for f in r["failing"]:
                lines.append(
                    f"| {f['id']} | {f['set']} | {f['group']} | {f['difficulty']} | "
                    f"{f['failed_checks']} |"
                )
        if r["errored"]:
            lines.append("")
            lines.append("## Errored rows (availability, not quality)")
            for e in r["errored"]:
                lines.append(f"- {e['id']}: {e['error']}")
        for label, ids in (
            ("Uncovered rows", r["uncovered"]),
            ("Stale rows", r["stale"]),
            ("Active cases not in this run", r["not_run"]),
        ):
            if ids:
                lines.append("")
                lines.append(f"## {label}")
                # A set-scoped run legitimately skips every other set; a
                # 400-id dump would drown the report, so collapse to per-set
                # counts once the listing stops being readable.
                if len(ids) > 25:
                    prefixes = Counter(i.rsplit("-", 1)[0] for i in ids)
                    lines.append(
                        f"{len(ids)} cases, by id prefix: "
                        + ", ".join(f"{p} ×{n}" for p, n in sorted(prefixes.items()))
                    )
                else:
                    lines.append(", ".join(ids))
        lines.append("")
    if len(rollups) > 1:
        configs = {
            (r["environment"], r["ff"], r["num_trials"], r["caseset_version"])
            for r in rollups
        }
        if len(configs) > 1:
            lines.append(
                "WARNING: runs differ in env/ff/trials/caseset_version - "
                "cross-run rates below are NOT comparable."
            )
            lines.append("")
        lines.append("## Cross-run rates (majority verdict)")
        set_names = sorted({s for r in rollups for s in r["by_set"]})
        lines.append("| run | overall | " + " | ".join(set_names) + " |")
        lines.append("|---" * (len(set_names) + 2) + "|")
        for r in rollups:
            cells = [_pct(r["overall"]["rate"])]
            for set_name in set_names:
                stat = r["by_set"].get(set_name)
                cells.append(_pct(stat["rate"]) if stat else "-")
            lines.append(f"| {r['run_id']} | " + " | ".join(cells) + " |")
        lines.append("")
        lines.extend(latency_comparison(rollups))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runs", nargs="+", type=Path, help="run JSON file(s)")
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/challenge"))
    parser.add_argument(
        "--targets",
        type=Path,
        default=None,
        help="targets YAML (default: <cases-dir>/TARGETS.yml)",
    )
    parser.add_argument("--json", type=Path, default=None, help="also write JSON here")
    args = parser.parse_args()

    cases_by_uid = {uid: case for _p, case, uid in load_store(args.cases_dir)}
    targets = load_targets(args.targets or args.cases_dir / "TARGETS.yml")
    rollups = []
    for path in args.runs:
        run = json.loads(path.read_text(encoding="utf-8"))
        rollups.append(rollup_run(run, cases_by_uid))
    print(render_markdown(rollups, targets))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"targets": targets, "runs": rollups}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {args.json}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
