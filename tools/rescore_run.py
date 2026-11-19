"""Recompute one deterministic check on a finished, uncommitted run.

    uv run python tools/rescore_run.py results/benchmark/runs/RUN.json
        --check chart_well_formed --note "<what changed in the check>"
        [--dry-run] [--artifacts-dir DIR]

For when a check had a bug and the run has not been committed yet. The check
is recomputed from each trial's saved agent state (the gzipped artifact the
harness wrote before it scored the trial), the per-trial scores are replaced,
and the merged `checks`, `reasons` and `buckets` are rebuilt with the
harness's own `merge_trials` and `summarize_buckets`. Nothing else in the
record changes. The record gains a `rescored` entry and a methodology note,
so a reader can tell the scores were recomputed and by which harness.

Run files are immutable once committed (results/README.md), so the tool
refuses a run file that git tracks at HEAD. An untracked or staged-only file
is rewritten in place. This differs from `compose_runs.py`, which never
writes to the ledger: composing mixes rows of different runs, while a
rescore keeps every row of one run and corrects one check on it.

Only checks that need nothing but the saved agent state are allowed (see
RESCORABLE). No LLM call, no network.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from goldset.buckets import row_verdict, summarize_buckets  # noqa: E402
from goldset.cli import REASON_TRIM, _harness_sha, merge_trials  # noqa: E402
from goldset.evaluators.output_checks import evaluate_chart_well_formed  # noqa: E402
from goldset.ledger import validate_run  # noqa: E402
from goldset.runner.artifacts import artifact_name  # noqa: E402


def _chart_well_formed(state: dict[str, Any]) -> tuple[float | None, str | None]:
    result = evaluate_chart_well_formed(state)
    return result["chart_well_formed_score"], result["chart_well_formed_reason"]


# Check name -> function(saved agent state) -> (score, reason). A check goes
# here only if the artifact holds everything it reads. Nothing that needs the
# case's expected values, a judge or the analytics API.
RESCORABLE: dict[str, Callable[[dict[str, Any]], tuple[float | None, str | None]]] = {
    "chart_well_formed": _chart_well_formed,
}

_TRIAL_ONLY_KEYS = ("checks", "trials", "error", "judge_errors", "no_answer")


class RescoreError(Exception):
    pass


def tracked_at_head(path: Path) -> bool:
    """True when git has this file in HEAD. A path outside any repo is not tracked."""
    done = subprocess.run(
        ["git", "-C", str(path.parent), "ls-tree", "--name-only", "HEAD", "--", path.name],
        capture_output=True, text=True,
    )
    return done.returncode == 0 and bool(done.stdout.strip())


def trial_entries(result: dict) -> list[dict]:
    """Rebuild the per-trial entries that `merge_trials` folded into `result`.

    The merged row keeps the last trial's entry (its reasons, actuals, trace
    URL), so the last rebuilt entry carries those; earlier trials keep only
    what the ledger stored for them.
    """
    trials = result.get("trials")
    if not trials:
        return [copy.deepcopy(result)]
    entries = []
    for index, trial in enumerate(trials):
        entry: dict[str, Any] = {"uid": result["uid"], "id": result["id"]}
        entry["checks"] = dict(trial["checks"])
        if trial.get("latency_s") is not None:
            entry["latency_s"] = trial["latency_s"]
        if trial.get("stream_s") is not None:
            entry["stream_s"] = trial["stream_s"]
        if trial.get("no_answer"):
            entry["no_answer"] = trial["no_answer"]
        if trial.get("error"):
            entry["error"] = trial["error"]
        if index == len(trials) - 1:
            for key, value in result.items():
                if key not in _TRIAL_ONLY_KEYS and key not in entry:
                    entry[key] = copy.deepcopy(value)
        entries.append(entry)
    return entries


def refold(entries: list[dict]) -> dict:
    """The merged row, by the harness's own merge. A one-trial row is its entry."""
    return merge_trials(entries)


def load_state(artifacts: Path, uid: str, trial: int) -> dict[str, Any]:
    path = artifacts / artifact_name(uid, trial)
    if not path.exists():
        raise RescoreError(f"missing artifact {path}")
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def rescore_result(result: dict, check: str, artifacts: Path) -> tuple[dict, int]:
    """The rescored row and how many of its trials changed."""
    recompute = RESCORABLE[check]
    entries = trial_entries(result)
    if refold(copy.deepcopy(entries)) != result:
        raise RescoreError(
            f"{result['id']}: cannot rebuild the merged row from its trials; "
            "refusing to rescore a row the harness's merge does not reproduce"
        )
    changed = 0
    for index, entry in enumerate(entries):
        old = entry["checks"].get(check)
        # Null means not evaluated: no charts, an accepted alternative path or
        # no reply. The saved state cannot tell which, so leave it null.
        if old is None:
            continue
        state = load_state(artifacts, result["uid"], index + 1)
        score, reason = recompute(state)
        if score is None:
            raise RescoreError(
                f"{result['id']} trial {index + 1}: scored {old} but the saved "
                "state gives no score; the artifact is not the state that was scored"
            )
        is_last = index == len(entries) - 1
        old_reason = (entry.get("reasons") or {}).get(check) if is_last else None
        new_reason = str(reason)[:REASON_TRIM] if reason else None
        if score == old and (not is_last or new_reason == old_reason):
            continue
        changed += 1
        entry["checks"][check] = score
        if is_last:
            reasons = dict(entry.get("reasons") or {})
            if new_reason:
                reasons[check] = new_reason
            else:
                reasons.pop(check, None)
            if reasons:
                entry["reasons"] = reasons
            else:
                entry.pop("reasons", None)
    if not changed:
        return result, 0
    return refold(entries), changed


def rescore_record(record: dict, check: str, artifacts: Path) -> tuple[dict, dict, list[dict]]:
    """The rescored record, its counts, and the rows whose verdict changed."""
    if summarize_buckets(record["results"]) != record["buckets"]:
        raise RescoreError(
            "the record's buckets do not match its results under the harness's "
            "summarize_buckets; refusing to rescore"
        )
    results, trials_changed, check_changed, verdict_changed = [], 0, [], []
    for result in record["results"]:
        new, changed = rescore_result(result, check, artifacts)
        results.append(new)
        trials_changed += changed
        if new["checks"].get(check) != result["checks"].get(check):
            check_changed.append(result["id"])
        before, after = row_verdict(result), row_verdict(new)
        if before != after:
            verdict_changed.append({"id": result["id"], "from": before, "to": after})
    out = dict(record)
    out["results"] = results
    out["buckets"] = summarize_buckets(results)
    counts = {
        "trials_changed": trials_changed,
        "check_verdicts_changed": len(check_changed),
        "overall_verdicts_changed": len(verdict_changed),
    }
    return out, counts, verdict_changed


def annotate(record: dict, check: str, note: str, counts: dict, sha: str, when: str) -> dict:
    """Add the `rescored` entry and the methodology note."""
    out = dict(record)
    out["rescored"] = [*record.get("rescored", []),
                       {"check": check, "harness_sha": sha, "at": when, "note": note, **counts}]
    sentence = f"{check} rescored at {sha} from the saved agent states: {note.rstrip('. ')}."
    note = record.get("methodology_note")
    if not note:
        out["methodology_note"] = sentence
    elif sentence not in note:
        out["methodology_note"] = f"{note} {sentence}"
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("run", type=Path, help="run record, results/<set>/runs/<run_id>.json")
    parser.add_argument("--check", required=True, help=f"one of: {', '.join(RESCORABLE)}")
    parser.add_argument("--note", help="what changed in the check (required unless --dry-run); "
                        "goes into methodology_note and the rescored entry")
    parser.add_argument("--dry-run", action="store_true", help="print the counts, write nothing")
    parser.add_argument("--artifacts-dir", type=Path,
                        help="the run's artifact folder; default <run dir>/../artifacts/<run_id>")
    args = parser.parse_args()

    if args.check not in RESCORABLE:
        print(f"error: {args.check!r} cannot be rescored from saved agent state; "
              f"allowed: {', '.join(RESCORABLE)}", file=sys.stderr)
        return 2
    if not args.dry_run and not (args.note or "").strip():
        print("error: --note is required: say what changed in the check", file=sys.stderr)
        return 2
    run_path = args.run.resolve()
    if not args.dry_run and tracked_at_head(run_path):
        print(f"error: {run_path} is tracked at HEAD. Run files are immutable once "
              "committed; rescore before committing, or follow results/README.md "
              "to delete the file visibly first.", file=sys.stderr)
        return 2
    record = json.loads(run_path.read_text(encoding="utf-8"))
    artifacts = args.artifacts_dir or run_path.parent.parent / "artifacts" / record["run_id"]
    try:
        new, counts, flipped = rescore_record(record, args.check, artifacts)
    except RescoreError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"{record['run_id']} {args.check}: {counts['trials_changed']} trial(s) changed, "
          f"{counts['check_verdicts_changed']} row check verdict(s) changed, "
          f"{counts['overall_verdicts_changed']} overall verdict(s) changed")
    for item in flipped:
        print(f"  {item['id']}: {item['from']} -> {item['to']}")
    passes = new["buckets"]["verdicts"]["pass"]
    print(f"pass: {record['buckets']['verdicts']['pass']} -> {passes} of {len(new['results'])}")
    if args.dry_run:
        return 0

    new = annotate(new, args.check, args.note.strip(), counts, _harness_sha(),
                   datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    problems = validate_run(new)
    if problems:
        print(f"error: rescored record is invalid: {problems}", file=sys.stderr)
        return 1
    run_path.write_text(json.dumps(new, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {run_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
