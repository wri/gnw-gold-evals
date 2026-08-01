"""Parity comparison for PR-08 step 1: old path vs new path, same build.

    uv run python tools/parity.py results/runs/<legacy-ingested>.json \
                                  results/runs/<gold-run>.json

Compares **majority verdicts on the legacy checks only** — the 16 checks
that exist on both paths (PR-04/06 checks don't exist in gnw-evals, and
info-only checks never carry a verdict). Every disagreement is listed with
both sides' reason strings; the acceptable class is judge-sampling noise,
and the table in the output is what goes into the PR-03 parity box.

Exit code is the gate: 0 only when at least one legacy check was compared
and no deterministic check disagreed. Zero comparable checks is a failure
in its own right — an empty comparison must never read as parity.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import INFO_ONLY, base_check_name
from goldset.ledger import read_run

# The checks the gnw-evals path can produce (PR-03 port surface, minus
# info-only). New-harness-only checks are excluded by construction.
LEGACY_CHECKS = frozenset(
    {
        "aoi_id_match",
        "dataset_id_match",
        "dataset_parameter_match",
        "context_layer_match",
        "date_extraction",
        "data_pull_exists",
        "charts_answer",
        "agent_answer",
        "expected_text_match",
        "clarification_requested",
        "suggested_datasets_match",
        "nudge_match",
        "dashboard_created",
        "dashboard_aoi_match",
        "dashboard_widgets_match",
        "dashboard_widgets_valid",
    }
) - INFO_ONLY

JUDGED = frozenset(
    {"charts_answer", "agent_answer", "expected_text_match",
     "clarification_requested"}
)


def _collapse_entry(entry: dict) -> tuple[dict, dict]:
    """Fold turn-prefixed check names (``t1.aoi_id_match``) onto their base
    names so multiturn rows compare against single-turn legacy rows instead
    of reading as spurious A=x B=None disagreements.

    Collision rule when several turns carry the same base check in one
    entry: **any-fail** — keep the worst turn's value (0.0 beats 1.0; None
    only when no turn evaluated the check), and keep the reason attached to
    the turn that supplied that value. A retirement gate must not hide a
    failing turn behind a passing sibling.
    """
    raw_reasons = entry.get("reasons") or {}
    checks: dict = {}
    reasons: dict = {}
    for name, value in (entry.get("checks") or {}).items():
        base = base_check_name(name)
        current = checks.get(base)
        if value is None:
            # Record the base name as seen, but never displace a real value.
            checks.setdefault(base, None)
            reasons.setdefault(base, raw_reasons.get(name))
            continue
        if current is None or value < current:
            checks[base] = value
            reasons[base] = raw_reasons.get(name)
    return checks, reasons


def compare(run_a: dict, run_b: dict) -> dict:
    index_a = {e["uid"]: e for e in run_a["results"] if e.get("uid")}
    index_b = {e["uid"]: e for e in run_b["results"] if e.get("uid")}
    shared = sorted(set(index_a) & set(index_b))
    agreements = 0
    comparable = 0
    disagreements = []
    for uid in shared:
        entry_a, entry_b = index_a[uid], index_b[uid]
        checks_a, reasons_a = _collapse_entry(entry_a)
        checks_b, reasons_b = _collapse_entry(entry_b)
        for check in sorted(LEGACY_CHECKS):
            value_a = checks_a.get(check)
            value_b = checks_b.get(check)
            if value_a is None and value_b is None:
                continue
            comparable += 1
            if value_a == value_b:
                agreements += 1
                continue
            disagreements.append(
                {
                    "id": entry_b.get("id") or entry_a.get("id"),
                    "uid": uid,
                    "check": check,
                    "judged": check in JUDGED,
                    "a": value_a,
                    "b": value_b,
                    "reason_a": reasons_a.get(check),
                    "reason_b": reasons_b.get(check),
                }
            )
    return {
        "shared_cases": len(shared),
        "comparable_checks": comparable,
        "agreements": agreements,
        "disagreements": disagreements,
    }


def _verdict(report: dict) -> str:
    if report["comparable_checks"] == 0:
        return (
            "NOTHING COMPARABLE — 0 shared legacy checks; "
            "parity is undemonstrated, do not retire the bridge"
        )
    if any(not d["judged"] for d in report["disagreements"]):
        return "PARITY BROKEN — deterministic checks disagree; do not retire the bridge"
    return "PARITY HOLDS — disagreements confined to judged checks"


def exit_code(report: dict) -> int:
    """The bridge-retirement gate: 0 only when something was actually
    compared and every deterministic check agreed."""
    if report["comparable_checks"] == 0:
        return 1
    return 1 if any(not d["judged"] for d in report["disagreements"]) else 0


def render(run_a: dict, run_b: dict, report: dict) -> str:
    deterministic_breaks = [d for d in report["disagreements"] if not d["judged"]]
    lines = [
        f"# Parity: {run_a['run_id']} (A, legacy path) vs {run_b['run_id']} (B, gold)",
        "",
        f"Shared cases {report['shared_cases']} · comparable legacy checks "
        f"{report['comparable_checks']} · agree {report['agreements']} · "
        f"disagree {len(report['disagreements'])} "
        f"({len(deterministic_breaks)} on deterministic checks)",
        "",
        f"**Verdict: {_verdict(report)}**",
    ]
    for item in report["disagreements"]:
        kind = "judged" if item["judged"] else "DETERMINISTIC"
        lines += [
            "",
            f"- [{kind}] {item['id']} `{item['check']}`: A={item['a']} B={item['b']}",
        ]
        if item["reason_a"]:
            lines.append(f"    - A: {item['reason_a'][:200]}")
        if item["reason_b"]:
            lines.append(f"    - B: {item['reason_b'][:200]}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_a", type=Path, help="legacy-path (ingested) run JSON")
    parser.add_argument("run_b", type=Path, help="gold-run JSON")
    args = parser.parse_args()
    run_a, run_b = read_run(args.run_a), read_run(args.run_b)
    report = compare(run_a, run_b)
    print(render(run_a, run_b, report))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
