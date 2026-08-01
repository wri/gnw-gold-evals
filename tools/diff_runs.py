"""Regression diff between two ledger runs.

    uv run python tools/diff_runs.py results/runs/A.json results/runs/B.json \
      [--json out.json] [--strict] [--fail-on-regression]

Comparison runs over the **intersection of uids** (stale rows excluded), so
case-set churn is reported but never counted as regression. Transitions per
check between run A (older) and run B (newer):

    regression        1.0 -> 0.0
    recovery          0.0 -> 1.0
    coverage gained   not evaluated -> evaluated
    coverage lost     evaluated -> not evaluated

``--strict`` refuses to compare runs with different caseset_versions.
``--fail-on-regression`` exits nonzero if any regression exists (CI gate).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.ledger import read_run

TRANSITIONS = ("regressions", "recoveries", "coverage_gained", "coverage_lost")


def indexable(run: dict) -> dict[str, dict]:
    return {
        entry["uid"]: entry
        for entry in run["results"]
        if entry.get("uid") and not entry.get("stale_case")
    }


def classify(prev: float | None, cur: float | None) -> str | None:
    if prev == 1.0 and cur == 0.0:
        return "regressions"
    if prev == 0.0 and cur == 1.0:
        return "recoveries"
    if prev is None and cur is not None:
        return "coverage_gained"
    if prev is not None and cur is None:
        return "coverage_lost"
    return None


def diff(run_a: dict, run_b: dict) -> dict:
    index_a, index_b = indexable(run_a), indexable(run_b)
    shared = sorted(set(index_a) & set(index_b))
    result: dict = {name: [] for name in TRANSITIONS}
    for uid in shared:
        entry_a, entry_b = index_a[uid], index_b[uid]
        for check in sorted(set(entry_a["checks"]) | set(entry_b["checks"])):
            kind = classify(entry_a["checks"].get(check), entry_b["checks"].get(check))
            if kind:
                item = {"uid": uid, "id": entry_b.get("id") or entry_a.get("id"), "check": check}
                if kind == "regressions":
                    reason = (entry_b.get("reasons") or {}).get(check)
                    if reason:
                        item["reason"] = reason
                result[kind].append(item)
    result["shared_cases"] = len(shared)
    result["only_in_a"] = len(set(index_a) - set(index_b))
    result["only_in_b"] = len(set(index_b) - set(index_a))
    result["stale_a"] = sum(1 for e in run_a["results"] if e.get("stale_case"))
    result["stale_b"] = sum(1 for e in run_b["results"] if e.get("stale_case"))
    return result


def render(run_a: dict, run_b: dict, report: dict) -> str:
    lines = [
        f"# {run_a['run_id']}  →  {run_b['run_id']}",
        "",
        f"Shared cases: {report['shared_cases']} "
        f"(identity churn: {report['only_in_a']} only in A, "
        f"{report['only_in_b']} only in B; "
        f"stale: {report['stale_a']}/{report['stale_b']})",
        "",
        f"**{len(report['regressions'])} regressions, "
        f"{len(report['recoveries'])} recoveries, "
        f"{len(report['coverage_gained'])} checks gained, "
        f"{len(report['coverage_lost'])} checks lost**",
    ]
    for kind, marker in (("regressions", "✗"), ("recoveries", "✓")):
        if report[kind]:
            lines += ["", f"## {kind}", ""]
            for item in report[kind]:
                line = f"- {marker} {item['id']} ({item['uid']}) `{item['check']}`"
                if item.get("reason"):
                    line += f" — {item['reason'][:160]}"
                lines.append(line)
    for kind in ("coverage_gained", "coverage_lost"):
        if report[kind]:
            lines += ["", f"## {kind.replace('_', ' ')}", ""]
            lines += [f"- {i['id']} `{i['check']}`" for i in report[kind]]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path, help="older run JSON")
    parser.add_argument("run_b", type=Path, help="newer run JSON")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    run_a, run_b = read_run(args.run_a), read_run(args.run_b)
    if run_a["caseset_version"] != run_b["caseset_version"]:
        message = (
            f"caseset_version differs: {run_a['caseset_version']} vs "
            f"{run_b['caseset_version']} — comparing uid intersection only"
        )
        if args.strict:
            print(f"refused (--strict): {message}")
            return 2
        print(f"note: {message}\n")

    report = diff(run_a, run_b)
    print(render(run_a, run_b, report))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")
    if args.fail_on_regression and report["regressions"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
