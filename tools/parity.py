"""Parity comparison for PR-08 step 1: old path vs new path, same build.

    uv run python tools/parity.py results/runs/<legacy-ingested>.json \
                                  results/runs/<gold-run>.json

Compares **majority verdicts on the legacy checks only** — the 17 checks
that exist on both paths (PR-04/06 checks don't exist in gnw-evals, and
info-only checks never carry a verdict). Every disagreement is listed with
both sides' reason strings; the acceptable class is judge-sampling noise,
and the table in the output is what goes into the PR-03 parity box.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import INFO_ONLY
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


def compare(run_a: dict, run_b: dict) -> dict:
    index_a = {e["uid"]: e for e in run_a["results"] if e.get("uid")}
    index_b = {e["uid"]: e for e in run_b["results"] if e.get("uid")}
    shared = sorted(set(index_a) & set(index_b))
    agreements = 0
    comparable = 0
    disagreements = []
    for uid in shared:
        entry_a, entry_b = index_a[uid], index_b[uid]
        for check in sorted(LEGACY_CHECKS):
            value_a = entry_a["checks"].get(check)
            value_b = entry_b["checks"].get(check)
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
                    "reason_a": (entry_a.get("reasons") or {}).get(check),
                    "reason_b": (entry_b.get("reasons") or {}).get(check),
                }
            )
    return {
        "shared_cases": len(shared),
        "comparable_checks": comparable,
        "agreements": agreements,
        "disagreements": disagreements,
    }


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
        "**Verdict: "
        + (
            "PARITY HOLDS — disagreements confined to judged checks"
            if not deterministic_breaks and report["comparable_checks"]
            else "PARITY BROKEN — deterministic checks disagree; do not retire the bridge"
        )
        + "**",
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
    return 1 if any(not d["judged"] for d in report["disagreements"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
