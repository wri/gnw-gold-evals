"""``gold`` — run the GOLD set against a live GNW API, writing the ledger.

    gold run --env staging --trials 3
    gold run --api-base-url https://api.staging.globalnaturewatch.org --id 1-030

Configuration policy (deliberately unlike gnw-evals): **flags always win.**
The environment supplies secrets only — ``API_TOKEN`` and
``ANTHROPIC_API_KEY`` (judge). No env var silently overrides a CLI default.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from goldset.adapter import case_to_expected
from goldset.buckets import summarize_buckets
from goldset.eval_types import TestResult
from goldset.ledger import majority, make_run_id, reason_name_from_column, write_run
from goldset.store import Case, load_store, read_manifest

ENV_URLS = {
    "staging": "https://api.staging.globalnaturewatch.org",
    "prod": "https://api.globalnaturewatch.org",
}
JUDGE_MODEL = "claude-haiku-4-5"
NON_CHECK_SCORES = {"overall_score"}
REASON_TRIM = 500


# Which actual_* diagnostics substantiate each check — recorded on the
# entry for FAILED checks only, so reports can show expected vs measured
# without re-running anything.
ACTUALS_FOR_CHECK = {
    "aoi_id_match": ("actual_id",),
    "dataset_id_match": ("actual_dataset_id",),
    "dataset_parameter_match": ("actual_dataset_parameters",),
    "context_layer_match": ("actual_context_layer",),
    "date_extraction": ("actual_extracted_start_date", "actual_extracted_end_date"),
    "date_coverage": ("actual_start_date", "actual_end_date"),
    "data_pull_exists": ("data_pull_error",),
    "agent_answer": ("actual_agent_answer",),
    "charts_answer": ("actual_charts_answer",),
    "expected_text_match": ("actual_agent_answer",),
    "clarification_requested": ("actual_clarification_requested",),
    "suggested_datasets_match": ("actual_suggested_datasets",),
    "nudge_match": ("actual_nudge_type", "actual_nudge_options"),
    "chart_type_match": ("actual_chart_type",),
    "scope_match": ("actual_scope",),
    "class_value_match": ("actual_class_values",),
    "answer_traceability": ("actual_traceability_claim",),
    "dashboard_created": ("actual_dashboard_created",),
    "dashboard_aoi_match": ("actual_dashboard_aoi_id", "actual_dashboard_aoi_count"),
    "dashboard_widgets_match": ("actual_dashboard_widget_types",),
    "web_fallback": ("actual_web_links",),
    "pull_source_match": ("actual_pull_source",),
}
ACTUAL_TRIM = 300


def _failed_actuals(dumped: dict, checks: dict) -> dict:
    actuals = {}
    for check, value in checks.items():
        if value != 0.0:
            continue
        parts = [
            str(dumped[field])
            for field in ACTUALS_FOR_CHECK.get(check, ())
            if dumped.get(field) not in (None, "")
        ]
        if parts:
            actuals[check] = " · ".join(parts)[:ACTUAL_TRIM]
    return actuals


def result_to_entry(result: TestResult, uid: str) -> dict:
    """Map one TestResult to one ledger entry (single trial)."""
    dumped = result.model_dump()
    checks = {
        key.removesuffix("_score"): value
        for key, value in dumped.items()
        if key.endswith("_score") and key not in NON_CHECK_SCORES
    }
    reasons = {}
    for key, value in dumped.items():
        check = reason_name_from_column(key)
        if check and value:
            reasons[check] = str(value)[:REASON_TRIM]

    entry: dict = {"uid": uid, "id": result.test_id, "checks": checks}
    if reasons:
        entry["reasons"] = reasons
    actuals = _failed_actuals(dumped, checks)
    if actuals:
        entry["actuals"] = actuals
    judge_errors = dumped.get("judge_errors") or []
    if judge_errors:
        entry["judge_errors"] = judge_errors
    if result.duration_seconds is not None:
        entry["latency_s"] = round(result.duration_seconds, 1)
    if result.trace_url:
        entry["trace_url"] = result.trace_url
    if result.error:
        entry["error"] = str(result.error)[:REASON_TRIM]
    return entry


def latency_info(latency_s: float | None, slow_threshold: float) -> dict | None:
    """G3: info-only slow flag for a merged entry — reported, never scored.

    Strictly over-threshold flags; at or under (or no recorded latency)
    returns None so no ``info`` key is written.
    """
    if latency_s is None or latency_s <= slow_threshold:
        return None
    return {"slow": True, "threshold_s": slow_threshold}


def merge_trials(entries: list[dict]) -> dict:
    """Fold per-trial entries into one: majority verdict + per-trial detail."""
    if len(entries) == 1:
        return entries[0]
    merged = dict(entries[-1])
    check_names = sorted({name for e in entries for name in e["checks"]})
    merged["checks"] = {
        name: majority([e["checks"].get(name) for e in entries])
        for name in check_names
    }
    merged["trials"] = [
        {"checks": e["checks"], "latency_s": e.get("latency_s")} for e in entries
    ]
    # Errors from ANY trial must survive the merge (PR-09 H3) — the base
    # copy above only carries the final trial's metadata.
    judge_errors = sorted({je for e in entries for je in e.get("judge_errors", [])})
    if judge_errors:
        merged["judge_errors"] = judge_errors
    else:
        merged.pop("judge_errors", None)
    errors = list(dict.fromkeys(e["error"] for e in entries if e.get("error")))
    if errors:
        merged["error"] = " | ".join(errors)[:500]
    else:
        merged.pop("error", None)
    return merged


def _harness_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
            cwd=Path(__file__).resolve().parents[2],
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def select_cases(args: argparse.Namespace) -> list[Case]:
    excluded = {s.strip().lower() for s in args.status_exclude.split(",") if s.strip()}
    cases = [case for _path, case, _uid in load_store(args.cases_dir)]
    cases = [c for c in cases if c.status.lower() not in excluded]
    if args.id:
        wanted = {i.lower() for i in args.id}
        cases = [c for c in cases if c.id.lower() in wanted]
    if args.group:
        cases = [c for c in cases if args.group.lower() in c.group.lower()]
    return sorted(cases, key=lambda c: c.id)


async def run_cases(args: argparse.Namespace, cases: list[Case]) -> list[dict]:
    # Deferred import: langchain/httpx stay out of store-only invocations.
    from goldset.runner.api import APITestRunner
    from goldset.runner.artifacts import ArtifactWriter
    from goldset.runner.multiturn import run_conversation

    runner = APITestRunner(
        api_base_url=args.resolved_url,
        api_token=os.environ.get("API_TOKEN"),
        ff=args.ff,
        verbose=args.verbose,
        wall_clock_limit=args.trial_timeout,
    )
    writer = ArtifactWriter(args.results_dir / "artifacts", args.run_id)
    # hard cap concurrency against the live API, as gnw-evals always did
    semaphore = asyncio.Semaphore(max(1, min(args.workers, 5)))

    async def run_one(case: Case) -> dict:
        async with semaphore:
            trials = []
            for trial in range(1, args.trials + 1):
                if case.is_multiturn:
                    trials.append(
                        await run_conversation(
                            runner,
                            case,
                            result_to_entry,
                            artifact_sink_factory=lambda n, c=case, t=trial: (
                                lambda a: writer(f"{c.uid}_turn{n}", t, a)
                            ),
                        )
                    )
                else:
                    result = await runner.run_test(
                        case.query,
                        case_to_expected(case),
                        artifact_sink=lambda a, c=case, t=trial: writer(c.uid, t, a),
                    )
                    trials.append(result_to_entry(result, case.uid))
            entry = merge_trials(trials)
            # G3: slow rows get an info flag — reported, never scored.
            info = latency_info(entry.get("latency_s"), args.slow_threshold)
            if info:
                entry["info"] = info
            clean = (
                all(v != 0.0 for v in entry["checks"].values())
                and not entry.get("error")
                and not entry.get("judge_errors")
            )
            print(f"  {case.id} [{'ok' if clean else 'FAIL'}]")
            return entry

    return list(await asyncio.gather(*(run_one(case) for case in cases)))


def prune_artifacts(results_dir: Path, keep_runs: int) -> int:
    """Artifacts are regenerable and unbounded (PR-09 H6): keep the newest
    N run directories (run_ids sort chronologically), delete the rest."""
    import shutil

    artifacts = results_dir / "artifacts"
    if not artifacts.exists():
        print("no artifacts directory; nothing to prune")
        return 0
    run_dirs = sorted(d for d in artifacts.iterdir() if d.is_dir())
    doomed = run_dirs[:-keep_runs] if keep_runs > 0 else run_dirs
    for directory in doomed:
        shutil.rmtree(directory)
        print(f"pruned {directory}")
    print(f"kept {len(run_dirs) - len(doomed)} run(s), pruned {len(doomed)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="gold", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run cases against a live API")
    run.add_argument("--env", choices=sorted(ENV_URLS), default="staging")
    run.add_argument("--api-base-url", default=None,
                     help="explicit URL; overrides --env")
    run.add_argument("--ff", default=None, help="agent tool profile")
    run.add_argument("--build", default="unknown",
                     help="agent build label, e.g. 'GNW 2026.7.29.1'")
    run.add_argument("--trials", type=int, default=1)
    run.add_argument("--workers", type=int, default=5)
    run.add_argument("--status-exclude", default="not doing")
    run.add_argument("--id", action="append", default=None,
                     help="run only this case id (repeatable)")
    run.add_argument("--group", default=None, help="substring match on group")
    run.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    run.add_argument("--results-dir", type=Path, default=Path("results"))
    run.add_argument("--slow-threshold", type=float, default=180.0,
                     help="seconds; slower rows get an info flag (never scored)")
    run.add_argument("--trial-timeout", type=float, default=900.0,
                     help="hard per-trial wall-clock limit in seconds; a trial "
                          "over it degrades to an error row (the per-read HTTP "
                          "timeout cannot bound a stream that keeps sending "
                          "keepalives)")
    run.add_argument("--note", default=None,
                     help="methodology note recorded on the run (e.g. after a "
                          "check-semantics change, so diffs aren't read as agent movement)")
    run.add_argument("--dry-run", action="store_true",
                     help="list selected cases without calling the API")
    run.add_argument("--verbose", action="store_true")

    prune = sub.add_parser(
        "prune-artifacts",
        help="delete raw artifact dirs beyond the newest N runs (ledger is untouched)",
    )
    prune.add_argument("--results-dir", type=Path, default=Path("results"))
    prune.add_argument("--keep-runs", type=int, default=5)
    args = parser.parse_args()

    if args.command == "prune-artifacts":
        return prune_artifacts(args.results_dir, args.keep_runs)

    manifest = read_manifest(args.cases_dir)
    if manifest is None:
        print(f"no manifest under {args.cases_dir}")
        return 1
    cases = select_cases(args)
    if not cases:
        print("no cases selected")
        return 1
    if args.dry_run:
        for case in cases:
            preview = case.query or (
                f"({len(case.turns)} turns) " + case.turns[0]["query"]
            )
            print(f"{case.id}  {case.uid}  [{case.status}] {preview[:70]}")
        print(f"{len(cases)} cases selected (dry run)")
        return 0
    # Secrets may live in .env (as in gnw-evals). Loaded here, before the
    # token check, and never used for anything but secrets — CLI defaults
    # still cannot be overridden by the environment.
    load_dotenv()
    if not os.environ.get("API_TOKEN"):
        print("API_TOKEN is not set (environment-specific machine token)")
        return 1

    args.resolved_url = args.api_base_url or ENV_URLS[args.env]
    environment = args.env if not args.api_base_url else (
        "prod" if "staging" not in args.api_base_url else "staging"
    )
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.run_id = make_run_id(started, environment, args.ff)

    print(f"run {args.run_id}: {len(cases)} cases x {args.trials} trial(s) "
          f"against {args.resolved_url}")
    entries = asyncio.run(run_cases(args, cases))

    run_record = {
        "run_id": args.run_id,
        "started": started,
        "environment": environment,
        "build": args.build,
        "ff": args.ff,
        "harness": {"repo": "gnw-gold-evals", "sha": _harness_sha()},
        "judge_model": JUDGE_MODEL,
        "num_trials": args.trials,
        "caseset_version": manifest["caseset_version"],
        "results": entries,
    }
    run_record["buckets"] = summarize_buckets(entries)
    if args.note:
        run_record["methodology_note"] = args.note
    path = write_run(args.results_dir, run_record)
    failed = sum(
        1 for e in entries
        if any(v == 0.0 for v in e["checks"].values()) or e.get("error")
    )
    judge_failures = sum(1 for e in entries if e.get("judge_errors"))
    line = f"wrote {path} — {len(entries)} cases, {failed} with failing checks"
    if judge_failures:
        line += f", {judge_failures} with JUDGE ERRORS (rerun before trusting)"
    print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
