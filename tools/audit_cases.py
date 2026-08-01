"""Case-set audit: depth, coverage floors, and DON'T violations.

    uv run python tools/audit_cases.py                # report (exit 0)
    uv run python tools/audit_cases.py --strict       # exit 1 on violations

Encodes the rules from ``cases/README.md`` and the acceptance criteria
from ``docs/caseset-implementation-plan.md`` (W1/W2/W3):

- depth: every ready/done/todo case implies >=2 checks across >=2 buckets
  (the ``metadata`` group is the sanctioned judged-only exception)
- coverage floors: every group and every dataset id >=3 rows
- DON'Ts: relative-date queries (tolerated when only routing is asserted),
  date expectations on non-date-scoped datasets, judged-only rows
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from goldset.buckets import buckets_for, implied_checks_for_case
from goldset.store import Case, load_store

COVERAGE_FLOOR = 3
EXEMPT_GROUPS = {"metadata"}  # sanctioned judged-only capability
EXCLUDED_STATUSES = {"not doing"}

# Alert/imagery datasets take genuinely date-scoped pulls; everything else
# is annual/fixed and must not carry date expectations (cases/README.md).
DATE_SCOPED_DATASET_IDS = {"0", "11"}
DATE_SCOPED_GROUPS = {"imagery"}

RELATIVE_DATE_RE = re.compile(
    r"\b(last|past|recent|latest|this (year|month|week))\b", re.IGNORECASE
)

# The rule (cases/README.md, DON'T #1): relative-date phrasing is tolerated
# only when the case asserts *routing alone* — which AOI/dataset/layer/
# parameters the agent selected, its scope, and whether it asked to clarify.
# Those stay true whatever the calendar says. Every other expectation
# (answers, dates, class values, chart/dashboard/nudge content, judged text,
# and any key added in the future) is presumed to drift with time or data
# versions and flags. Allow-list rather than deny-list so that new
# expectation vocabulary fails safe.
ROUTING_ONLY_FIELDS = {
    "aoi_ids", "aoi_source", "dataset_id", "dataset_name",
    "dataset_parameters", "context_layer", "scope", "clarification",
}

DETERMINISTIC_FIELDS = {
    "aoi_ids", "dataset_id", "dataset_parameters", "context_layer",
    "start_date", "end_date", "suggested_datasets", "nudge_type",
    "nudge_options", "dashboard_created", "dashboard_widgets",
    "scope", "chart_type", "class_values", "clarification",
}


def _queries(case: Case) -> list[str]:
    if case.is_multiturn:
        return [turn["query"] for turn in case.turns]
    return [case.query]


def _expected_maps(case: Case) -> list[dict[str, str]]:
    if case.is_multiturn:
        return [turn.get("expected") or {} for turn in case.turns]
    return [case.expected]


def _dataset_alternatives(case: Case) -> set[str]:
    ids: set[str] = set()
    for expected in _expected_maps(case):
        for alt in str(expected.get("dataset_id", "")).split(";"):
            if alt.strip():
                ids.add(alt.strip())
    return ids


def depth_violation(case: Case) -> str | None:
    if case.group in EXEMPT_GROUPS:
        return None
    implied = implied_checks_for_case(case)
    buckets = {b for check in implied for b in buckets_for(check)}
    if len(implied) >= 2 and len(buckets) >= 2:
        return None
    return (
        f"{case.id}: implies {len(implied)} check(s) in {len(buckets)} "
        f"bucket(s) — needs >=2 in >=2"
    )


def _turn_deltas(case: Case) -> list[dict]:
    if case.is_multiturn:
        return [turn.get("deltas") or {} for turn in case.turns]
    return [{}]


def dont_violations(case: Case) -> list[str]:
    problems = []
    for query, expected, deltas in zip(
        _queries(case), _expected_maps(case), _turn_deltas(case)
    ):
        match = RELATIVE_DATE_RE.search(query)
        if match:
            drifting = sorted(
                key for key, value in expected.items()
                if str(value).strip() and key not in ROUTING_ONLY_FIELDS
            )
            if drifting:
                problems.append(
                    f"{case.id}: relative-date phrasing ({match.group(0)!r}) "
                    f"with non-routing expectation(s) {drifting}"
                )
        has_dates = expected.get("start_date") or expected.get("end_date")
        if has_dates and case.group not in DATE_SCOPED_GROUPS:
            alternatives = {
                a.strip() for a in str(expected.get("dataset_id", "")).split(";")
                if a.strip()
            }
            # Every alternative must be date-scoped: "4;11" may resolve to
            # the annual dataset 4, so a mixed list is as unsafe as a bare 4.
            if alternatives and not alternatives <= DATE_SCOPED_DATASET_IDS:
                problems.append(
                    f"{case.id}: date expectations on non-date-scoped "
                    f"dataset(s) {sorted(alternatives)}"
                )
        judged_only = (
            (expected.get("answer") or expected.get("text"))
            and not (set(expected) & DETERMINISTIC_FIELDS)
            and not deltas  # a turn asserting state deltas is deterministic
        )
        if judged_only and case.group not in EXEMPT_GROUPS:
            problems.append(f"{case.id}: judged-only expectations")
    return problems


def audit(cases: list[Case]) -> dict:
    active = [c for c in cases if c.status.lower() not in EXCLUDED_STATUSES]
    group_counts = Counter(c.group for c in active)
    dataset_counts: Counter = Counter()
    for case in active:
        for dataset_id in _dataset_alternatives(case):
            dataset_counts[dataset_id] += 1

    return {
        "active": len(active),
        "parked": len(cases) - len(active),
        "depth": [v for c in active if (v := depth_violation(c))],
        "donts": [p for c in active for p in dont_violations(c)],
        "thin_groups": {
            g: n for g, n in sorted(group_counts.items()) if n < COVERAGE_FLOOR
        },
        "thin_datasets": {
            d: n for d, n in sorted(dataset_counts.items()) if n < COVERAGE_FLOOR
        },
    }


def _section(items: list[str]) -> list[str]:
    return items or ["- none"]


def render(report: dict) -> str:
    lines = [
        "# Case-set audit",
        "",
        f"Active cases: {report['active']} (+{report['parked']} parked)",
        "",
        f"## Depth violations ({len(report['depth'])})",
        *_section([f"- {v}" for v in report["depth"]]),
        "",
        f"## DON'T violations ({len(report['donts'])})",
        *_section([f"- {v}" for v in report["donts"]]),
        "",
        f"## Groups below the floor of {COVERAGE_FLOOR}",
        *_section([f"- {g}: {n}" for g, n in report["thin_groups"].items()]),
        "",
        f"## Datasets below the floor of {COVERAGE_FLOOR}",
        *_section([f"- id {d}: {n}" for d, n in report["thin_datasets"].items()]),
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", type=Path, default=Path("cases/v2"))
    parser.add_argument("--strict", action="store_true",
                        help="exit 1 on depth/DON'T violations (coverage floors "
                             "stay report-only until W1 lands)")
    args = parser.parse_args(argv)

    cases = [case for _p, case, _u in load_store(args.cases_dir)]
    report = audit(cases)
    print(render(report))
    if args.strict and (report["depth"] or report["donts"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
