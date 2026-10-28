"""Write the page data for one BENCHMARK run: the precomputed numbers behind
the accuracy-benchmarks page in project-zeno-next.

    uv run python tools/benchmark_page.py results/benchmark/runs/<run_id>.json

Writes ``results/benchmark/pages/<run_id>.json``. Run it right after the
run, on the machine that ran it: the per-attempt summaries ("what the agent
did") come from the run's agent-state artifacts
(``results/benchmark/artifacts/<run_id>/``), which are gitignored, so the
page cannot be rebuilt from the repo alone. The page is derived, like
``results/index.json``; commit it with the run and regenerate the index.

Rates use the BENCHMARK semantics (``benchmarks/README.md``): a question is
complete when it passes in the majority of trials (``majority``); the page
headline is the share right on **every** trial (``every_time``), with
``any_time`` (right on at least one) alongside. An attempt that got no reply
is a wrong attempt (``attempt_errors`` kind ``no_answer``); one the harness
could not score is left out (kind ``unscored``), and a question with none
scored is an error and leaves the denominator. Failures are attributed to their earliest failing stage
(``tools/challenge_rollup.py``). Groups by type and use case come from the
manifest's frozen member facets, never the live case.

Every group (``summary``, ``types[]``, ``use_cases[]``) carries
``failure_modes`` (where the questions that fail the majority verdict went
wrong) and ``failure_modes_by_standard``: the same counts for each accuracy
standard, ``every_time``, ``majority`` and ``any_time``. A question is wrong
under ``every_time`` when not every trial is right, under ``majority`` when
its verdict is fail (so ``majority`` equals ``failure_modes``), and under
``any_time`` when no trial is right. It counts at
``challenge_rollup.failure_stage``, the same stage under every standard, so
a stricter standard only adds questions. Keys follow ``ATTRIBUTION``; zero
counts are left out. Each standard's counts sum to the scored questions
less that standard's accurate ones.

**Combined pages** (``--base <earlier run>``, repeatable): after a few
members' cases are revised, rerun only those members (``gold run --benchmark
<v> --missing-from <earlier run>``) and write the page from the rerun plus
the earlier runs' results for every other member, matched by uid; a newer
run wins where two measured the same uid. All runs must share environment,
ff and trial count, and together cover every active member. The page's
``run`` block describes the rerun and adds ``sources`` (each run's id, start
time and question count, oldest first); every question carries the
``run_id`` it came from. ``tools/build_run_index.py`` reads
``sources`` to judge the combination canonical.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import challenge_rollup as cr  # noqa: E402

from goldset.benchmark import (  # noqa: E402
    STAGE_ORDER,
    USE_CASES,
    Benchmark,
    load_benchmark,
    manifest_sha,
)
from goldset.buckets import (  # noqa: E402
    DEDICATED,
    base_check_name,
    buckets_for,
    is_info_only,
    row_verdict,
)
from goldset.store import Case, load_store  # noqa: E402

SCHEMA_VERSION = 1
ATTRIBUTION = (*STAGE_ORDER, "unattributed")

DATASETS = {"1": "Land cover", "2": "Grasslands", "3": "Natural lands", "4": "Tree cover loss",
            "5": "Tree cover gain", "6": "GHG net flux", "7": "Tree cover", "8": "Loss drivers",
            "9": "Commodity emissions (sLUC)", "10": "Loss from fires", "11": "Disturbance alerts"}
TYPE_DESCRIPTIONS = {
    "geospatial": "finding the place", "dataset": "finding the right data",
    "quantification": "how much, how many", "comparison": "places or periods",
    "trend": "change over time", "monitoring": "recent alerts in an area",
    "portfolio": "many areas at once", "causal": "why it happened",
    "refusal": "declining or asking back", "identification": "what is at this place",
    "risk": "exposure and threat", "conceptual": "definitions and methods",
    "feasibility": "can it be done here",
}
# The sheet's AOI types (case notes.aoi_type) as reader-facing place kinds.
PLACES = {
    "Country": "Country", "Subnational": "Sub-national area",
    "Multiple named areas": "Several named areas", "Portfolio / many areas": "Many areas",
    "None (data or method question)": "No place named", "Protected area": "Protected area",
    "Indigenous / community territory": "Indigenous or community land",
    "Global / regional / biome": "Global or regional", "Point": "A point",
    "Other (concession, project area, landscape)": "Other area",
    "Custom area (fixture)": "Own area",
}
ANSWER_EXCERPT_CHARS = 220


def trial_ok(trial: dict[str, Any]) -> bool:
    """A trial is right when every gating check it evaluated passed; one
    that got no reply evaluated none, so it is wrong."""
    checks = {k: v for k, v in (trial.get("checks") or {}).items()
              if not is_info_only(k) and v is not None}
    return bool(checks) and all(v == 1.0 for v in checks.values())


def scored_trials(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """The attempts that count: all but those the harness could not score."""
    return [t for t in entry["trials"] if not t.get("error")]


def attempt_error(trial: dict[str, Any]) -> dict[str, str] | None:
    if trial.get("no_answer"):
        return {"kind": "no_answer", "reason": trial["no_answer"]}
    if trial.get("error"):
        return {"kind": "unscored", "reason": trial["error"]}
    return None


def group_stats(entries: list[dict[str, Any]]) -> dict[str, Any]:
    verdicts = [row_verdict(e) for e in entries]
    scored = [e for e, v in zip(entries, verdicts) if v in ("pass", "fail")]
    n = len(scored)
    passed = sum(1 for v in verdicts if v == "pass")
    every = sum(1 for e in scored if all(trial_ok(t) for t in scored_trials(e)))
    any_ = sum(1 for e in scored if any(trial_ok(t) for t in scored_trials(e)))
    modes = collections.Counter(cr.primary_failure(e) for e, v in zip(entries, verdicts) if v == "fail")
    wrong = {
        "every_time": lambda e: not all(trial_ok(t) for t in scored_trials(e)),
        "majority": lambda e: row_verdict(e) == "fail",
        "any_time": lambda e: not any(trial_ok(t) for t in scored_trials(e)),
    }
    by_standard = {}
    for standard, is_wrong in wrong.items():
        stages = collections.Counter(cr.failure_stage(e) for e in scored if is_wrong(e))
        by_standard[standard] = {s: stages[s] for s in ATTRIBUTION if stages[s]}
    return {
        "scored": n,
        "errors": verdicts.count("error"),
        "attempts": sum(len(e["trials"]) for e in entries),
        "no_answer": sum(1 for e in entries for t in e["trials"] if t.get("no_answer")),
        "passed": passed,
        "majority": passed / n if n else None,
        "every_time": every / n if n else None,
        "any_time": any_ / n if n else None,
        "failure_modes": {s: modes[s] for s in ATTRIBUTION if modes[s]},
        "failure_modes_by_standard": by_standard,
    }


def place_kind(case: Case) -> str:
    if case.notes.get("aoi_type"):
        return PLACES[case.notes["aoi_type"]]
    # The first alternative stands for the place (``|`` separates alternatives).
    first_alternative = (case.expected.get("aoi_ids") or "").split("|")[0]
    ids = [i.strip() for i in first_alternative.split(";") if i.strip()]
    if not ids:
        return "No place named"
    # An area may list equivalent records with ``/``; the first stands for it.
    first = ids[0].split("/")[0].strip()
    if re.fullmatch(r"\d+", first):
        return "Protected area"
    if re.fullmatch(r"[A-Z]{3}\d{3,5}", first):
        return "Indigenous or community land"
    if re.fullmatch(r"[A-Z]{3}", first):
        return "Country" if len(ids) < 5 else "Many areas"
    return "Sub-national area"


def dataset_names(case: Case) -> list[str]:
    ids = {d.strip() for d in (case.expected.get("dataset_id") or "").split(";")}
    return sorted(DATASETS[d] for d in ids if d in DATASETS)


def composition(members, cases: dict[str, Case]) -> dict[str, Any]:
    picked = [cases[m.uid] for m in members]
    return {
        "types": collections.Counter(m.type for m in members).most_common(),
        "places": collections.Counter(place_kind(c) for c in picked).most_common(),
        "datasets": collections.Counter(d for c in picked for d in dataset_names(c)).most_common(5),
        "synthetic": sum(1 for m in members if m.synthetic),
    }


def attempt_summary(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the agent did on one attempt, from its final state."""
    if state is None:
        return None
    dataset = state.get("dataset") or {}
    aois = (state.get("aoi_selection") or {}).get("aois", [])
    answer = re.sub(r"\s+", " ", (state.get("final_answer") or "").replace("*", "").replace("#", "")).strip()
    return {
        "tools": [call["name"] for call in state.get("tool_calls") or []],
        "aoi_ids": [a.get("src_id") for a in aois],
        "dataset_id": dataset.get("dataset_id"),
        "context_layer": dataset.get("context_layer"),
        "dates": [dataset.get("start_date"), dataset.get("end_date")] if dataset.get("start_date") else None,
        "nudge": (state.get("nudge") or {}).get("type") or None,
        "charts": len(state.get("charts_data") or []),
        "answer_excerpt": answer[:ANSWER_EXCERPT_CHARS],
    }


def load_attempts(artifacts: Path, uid: str, trials: int) -> list[dict[str, Any] | None]:
    """Trial 1 is ``<uid>.json.gz``, later trials ``<uid>_t<n>.json.gz``."""
    out = []
    for i in range(trials):
        path = artifacts / f"{uid}{'' if i == 0 else f'_t{i + 1}'}.json.gz"
        out.append(attempt_summary(json.load(gzip.open(path)) if path.exists() else None))
    return out


def failed_checks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Gating checks that failed on at least one trial."""
    out = []
    for check, final in sorted((entry.get("checks") or {}).items()):
        if is_info_only(check) or final is None:
            continue
        per_trial = [(t.get("checks") or {}).get(check) for t in entry["trials"]]
        if 0.0 not in per_trial:
            continue
        out.append({
            "check": check,
            "stage": DEDICATED.get(base_check_name(check), "shared"),
            "verdict": "fail" if final == 0.0 else "pass",
            "per_trial": [None if v is None else v == 1.0 for v in per_trial],
            "actual": (entry.get("actuals") or {}).get(check),
            "reason": (entry.get("reasons") or {}).get(check),
        })
    return out


def stage_checks(members, by_uid) -> dict[str, dict[str, int]]:
    out = {}
    for stage in STAGE_ORDER:
        checked = passed = first = 0
        for m in members:
            entry = by_uid[m.uid]
            values = [v for k, v in entry["checks"].items()
                      if stage in buckets_for(k) and v is not None and not is_info_only(k)]
            if values:
                checked += 1
                passed += all(v == 1.0 for v in values)
            if row_verdict(entry) == "fail" and cr.primary_failure(entry) == stage:
                first += 1
        out[stage] = {"checked": checked, "passed": passed, "first_failures": first}
    return out


def combine(run: dict[str, Any], artifacts: Path, bases: list[tuple[dict[str, Any], Path]]
            ) -> tuple[dict[str, dict], dict[str, tuple[str, Path]]]:
    """Results by uid, and each uid's (run_id, artifacts dir). The newest
    run that measured a uid wins: bases oldest first, then the rerun."""
    by_uid: dict[str, dict] = {}
    source: dict[str, tuple[str, Path]] = {}
    for r, art in (*sorted(bases, key=lambda b: b[0]["started"]), (run, artifacts)):
        for e in r.get("results", []):
            by_uid[e["uid"]] = e
            source[e["uid"]] = (r["run_id"], art)
    return by_uid, source


def build_page(run: dict[str, Any], bench: Benchmark, cases: dict[str, Case],
               artifacts: Path, bases: list[tuple[dict[str, Any], Path]] = ()) -> dict[str, Any]:
    by_uid, source = combine(run, artifacts, bases)
    if bases:
        uncovered = [m.id for m in bench.active_members if m.uid not in by_uid]
        if uncovered:
            runs = ", ".join(r["run_id"] for r, _ in bases)
            raise SystemExit(f"{len(uncovered)} active member(s) in neither {run['run_id']} "
                             f"nor its bases ({runs}): {uncovered[:5]}")
    members = [m for m in bench.active_members if m.uid in by_uid]
    missing = [m.id for m in members if m.uid not in cases]
    if missing:
        raise SystemExit(f"member cases not in the store (edited since the run?): {missing[:5]}")
    trials = int(run["num_trials"])

    types = []
    for qtype in bench.types:
        mine = [m for m in members if m.type == qtype["key"]]
        row = {"key": qtype["key"], "label": qtype["label"],
               "description": TYPE_DESCRIPTIONS.get(qtype["key"], ""), "measured": bool(mine)}
        if mine:
            entries = [by_uid[m.uid] for m in mine]
            row.update(group_stats(entries))
            row["stage_checks"] = stage_checks(mine, by_uid)
            good = next((m for m in mine if cr.strict_clean(by_uid[m.uid])), None)
            bad = next((m for m in mine if row_verdict(by_uid[m.uid]) == "fail"), None)
            row["example_pass"] = cases[good.uid].query if good else None
            row["example_fail"] = {
                "query": cases[bad.uid].query,
                "failed_checks": sorted(k for k, v in by_uid[bad.uid]["checks"].items()
                                        if v == 0.0 and not is_info_only(k)),
            } if bad else None
        types.append(row)

    use_cases = []
    for key, label in USE_CASES.items():
        mine = [m for m in members if key in m.use_cases]
        if mine:
            use_cases.append({"key": key, "label": label,
                              **group_stats([by_uid[m.uid] for m in mine]),
                              "composition": composition(mine, cases)})

    entries = [by_uid[m.uid] for m in members]
    complete = [e for e in entries if row_verdict(e) == "pass"]
    questions = []
    for m in members:
        entry, case = by_uid[m.uid], cases[m.uid]
        verdict = row_verdict(entry)
        expected = {k: v for k, v in case.expected.items() if k != "forbidden_tools"}
        if "forbidden_tools" in case.expected:
            expected["forbidden_tools"] = f"({len(case.expected['forbidden_tools'].split(';'))} tools)"
        questions.append({
            "id": m.id, "uid": m.uid, "benchmark_id": m.benchmark_id,
            "type": m.type, "cohort": m.cohort, "difficulty": m.difficulty,
            "query": case.query,
            "verdict": verdict,
            "trials_right": [trial_ok(t) for t in entry["trials"]],
            "attempt_errors": [attempt_error(t) for t in entry["trials"]],
            "consistent": cr.strict_clean(entry),
            "primary_failure": cr.primary_failure(entry) if verdict == "fail" else None,
            "failed_checks": failed_checks(entry),
            "expected": expected,
            "drafted": "draft" in case.notes.get("expectations", ""),
            "run_id": source[m.uid][0],
            "attempts": load_attempts(source[m.uid][1], m.uid, trials),
            "trace_url": entry.get("trace_url"),
            "place": place_kind(case),
            "use_cases": list(m.use_cases),
            "synthetic": m.synthetic,
        })

    run_block = {"run_id": run["run_id"], "started": run["started"],
                 "environment": run.get("environment"), "ff": run.get("ff"),
                 "num_trials": trials, "harness_sha": (run.get("harness") or {}).get("sha")}
    if bases:
        counts = collections.Counter(source[m.uid][0] for m in members)
        ordered = [*sorted((b for b, _ in bases), key=lambda b: b["started"]), run]
        run_block["sources"] = [{"run_id": r["run_id"], "started": r["started"],
                                 "questions": counts[r["run_id"]]} for r in ordered]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "tools/benchmark_page.py",
        "run": run_block,
        "benchmark": {"version": bench.version, "status": bench.status,
                      "manifest_sha": run["benchmark"]["manifest_sha"],
                      "members": len(bench.active_members),
                      "excluded": len(bench.raw.get("sampling", {}).get("excluded", []))},
        "summary": {
            **group_stats(entries),
            "consistency": {"complete": len(complete),
                            "clean": sum(cr.strict_clean(e) for e in complete)},
            "attempt_rates": [sum(trial_ok(e["trials"][i]) for e in entries) / len(entries)
                              for i in range(trials)],
            "datasets_covered": len({d for m in members for d in dataset_names(cases[m.uid])}),
        },
        "stages": [{"key": s, **stage_checks(members, by_uid)[s]} for s in STAGE_ORDER],
        "unattributed": sum(1 for e in entries
                            if row_verdict(e) == "fail" and cr.primary_failure(e) == "unattributed"),
        "types": types,
        "use_cases": use_cases,
        "questions": questions,
    }


def run_artifacts(root: Path, run: dict[str, Any]) -> Path:
    artifacts = root / "results" / "benchmark" / "artifacts" / run["run_id"]
    if not artifacts.is_dir():
        raise SystemExit(f"{artifacts} not found: write the page on the machine that ran the run")
    return artifacts


def check_base(base: dict[str, Any], run: dict[str, Any]) -> None:
    """A base run may only fill in for the rerun when the two measured the
    same way; it may come from an earlier manifest, since results match by uid."""
    if "benchmark" not in base:
        raise SystemExit(f"base {base.get('run_id')} is not a benchmark run")
    for field in ("environment", "ff", "num_trials"):
        if base.get(field) != run.get(field):
            raise SystemExit(f"base {base['run_id']} has {field}={base.get(field)!r}, "
                             f"the rerun {run.get(field)!r}: they cannot be combined")
    if base["started"] >= run["started"]:
        raise SystemExit(f"base {base['run_id']} must be older than {run['run_id']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", type=Path, help="results/benchmark/runs/<run_id>.json")
    parser.add_argument("--base", type=Path, action="append", default=[], metavar="RUN",
                        help="an earlier benchmark run whose results fill every member "
                             "this run did not measure (a combined page); repeatable, "
                             "the newest run wins where two measured a member")
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    args = parser.parse_args()

    root = args.repo_root
    run = json.loads(args.run.read_text(encoding="utf-8"))
    if "benchmark" not in run:
        raise SystemExit(f"{args.run} is not a benchmark run")
    manifest = root / run["benchmark"]["path"]
    if manifest_sha(manifest) != run["benchmark"]["manifest_sha"]:
        raise SystemExit(f"{manifest} changed since run {run['run_id']} (manifest_sha differs); "
                         "its member facets may no longer describe the run")
    artifacts = run_artifacts(root, run)
    bases = []
    for path in args.base:
        base = json.loads(path.read_text(encoding="utf-8"))
        check_base(base, run)
        bases.append((base, run_artifacts(root, base)))
    bench = load_benchmark(manifest)
    cases = {uid: c for _p, c, uid in load_store(root / bench.source["cases_dir"])}
    page = build_page(run, bench, cases, artifacts, bases)

    out = root / "results" / "benchmark" / "pages" / f"{run['run_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(page, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    s = page["summary"]
    print(f"wrote {out}: every time {s['every_time']:.1%}, majority {s['majority']:.1%} "
          f"({s['passed']}/{s['scored']}), {s['errors']} errored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
