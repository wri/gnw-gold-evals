"""Attempts and questions to outcomes: right, wrong, declined or uncovered.

An attempt's outcome combines its reply checks with its decline label:

- no reply (Horizon's timeouts, Sonnet's $1 stop): wrong, as BENCHMARK
  counts it;
- asked back: right when it offers every accepted choice (the accepted-nudge
  check for Horizon, the offer judge for Sonnet), else as a decline;
- declined: where the overlay says a decline is the right answer, right
  unless a check failed, and then wrong (a decline can mislead too: an
  invented WhatsApp setting); elsewhere declined;
- answered: right when every scored gating check passed; uncovered when
  none scored; declined when the only failure is a figure the reply never
  stated (an honest omission, not an error); otherwise wrong.

A wrong figure is an answer that states its own figure for what was asked
and misses it. Pilot fixes agreed by AJ, 2026-10-30.

A question takes right when most of its scored attempts are right (ties
fail, as in BENCHMARK); otherwise declined or wrong, whichever is commoner,
a tie counting as wrong; uncovered when no attempt scored. Beside it rides
the BENCHMARK-style verdict: the same attempts handed to the harness's own
``buckets.row_verdict``, which ignores the label, so the extra outcomes hide
nothing and the column follows BENCHMARK's rule if that rule changes.

The stricter reading AJ asked to headline beside it (2026-10-30): right on
every attempt, so an attempt no check applied to also falls short, and a
wrong figure on any attempt, the risk a user meets on asking once.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable
from typing import Any

from goldset.buckets import row_verdict
from goldset.ledger import majority
from goldset.plain.overlay import Calls

GATING = ("expected_text_match", "figure_match", "figure_claim_match", "answer_period_match")
FIGURE_CHECKS = ("figure_match", "figure_claim_match")
OUTCOMES = ("right", "wrong", "declined", "uncovered")


def gating(calls: Calls) -> tuple[str, ...]:
    """The reply checks that decide a verdict once the overlay has spoken."""
    dropped = set()
    if calls.text == "horizon_only":
        dropped.add("expected_text_match")
    if calls.figure_info_only:
        dropped.update(FIGURE_CHECKS)
    return tuple(c for c in GATING if c not in dropped)


def checks_verdict(checks: dict[str, Any], calls: Calls) -> str | None:
    scored = [checks.get(c) for c in gating(calls) if checks.get(c) is not None]
    if not scored:
        return None
    return "fail" if any(value == 0.0 for value in scored) else "pass"


def attempt_outcome(attempt: dict[str, Any], calls: Calls) -> str | None:
    """One attempt's outcome; None when the harness could not score it."""
    if attempt.get("no_answer"):
        return "wrong"
    if attempt.get("error"):
        return None
    label = attempt.get("label")
    if label == "asked_back" and attempt.get("offer") == 1.0:
        return "right"
    checks = attempt.get("checks") or {}
    verdict = checks_verdict(checks, calls)
    if label in ("declined", "asked_back"):
        if not calls.decline_right:
            return "declined"
        return "wrong" if verdict == "fail" else "right"
    if verdict is None:
        return "uncovered"
    if verdict == "pass":
        return "right"
    failed = {c for c in gating(calls) if checks.get(c) == 0.0}
    if failed == {"figure_match"} and attempt.get("gives_figure") is False:
        return "declined"
    return "wrong"


def as_trial(attempt: dict[str, Any], calls: Calls) -> dict[str, Any]:
    """An attempt in the harness's trial shape. An offer stands in for the
    accepted-nudge path, where BENCHMARK leaves the reply checks null."""
    if attempt.get("offer") is not None:
        checks = {"accepted_nudge_match": attempt["offer"]}
    else:
        checks = {c: (attempt.get("checks") or {}).get(c) for c in gating(calls)}
    return {"checks": checks, "no_answer": bool(attempt.get("no_answer")),
            "error": attempt.get("error")}


def wrong_figure(attempt: dict[str, Any], calls: Calls) -> bool:
    """An answer whose figure check failed: the clearest way to mislead."""
    return (
        attempt.get("label") == "answered"
        and attempt.get("gives_figure") is not False
        and "figure_match" in gating(calls)
        and (attempt.get("checks") or {}).get("figure_match") == 0.0
    )


def question(attempts: list[dict[str, Any]], calls: Calls) -> dict[str, Any]:
    """A question's outcome, BENCHMARK-style verdict and wrong-figure flag."""
    outcomes = [attempt_outcome(a, calls) for a in attempts]
    scored = [(a, o) for a, o in zip(attempts, outcomes, strict=True)
              if o in ("right", "wrong", "declined")]
    if not scored:
        outcome = "uncovered"
    elif majority([1.0 if o == "right" else 0.0 for _, o in scored]) == 1.0:
        outcome = "right"
    else:
        outcome = "declined" if outcomes.count("declined") > outcomes.count("wrong") else "wrong"
    figures_wrong = [wrong_figure(a, calls) for a, _ in scored]
    return {
        "outcome": outcome,
        "benchmark": row_verdict({"trials": [as_trial(a, calls) for a in attempts]}),
        "wrong_figure": majority([1.0 if w else 0.0 for w in figures_wrong]) == 1.0,
        "right_every_time": bool(attempts) and all(o == "right" for o in outcomes),
        "wrong_figure_any": any(figures_wrong),
    }


def summarise(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Counts and shares over every question, uncovered included."""
    results = list(results)
    total = len(results)
    counts = Counter(r["outcome"] for r in results)
    wrong_figures = sum(r["wrong_figure"] for r in results)
    every_time = sum(r["right_every_time"] for r in results)
    any_wrong_figure = sum(r["wrong_figure_any"] for r in results)
    benchmark_passes = sum(r["benchmark"] == "pass" for r in results)

    def share(n: int) -> float:
        return round(n / total, 4) if total else 0.0

    return {
        "questions": total,
        **{o: counts.get(o, 0) for o in OUTCOMES},
        "rates": {o: share(counts.get(o, 0)) for o in OUTCOMES},
        "wrong_figure": wrong_figures,
        "wrong_figure_rate": share(wrong_figures),
        "right_every_time": every_time,
        "right_every_time_rate": share(every_time),
        "wrong_figure_any": any_wrong_figure,
        "wrong_figure_any_rate": share(any_wrong_figure),
        "benchmark_style_pass": benchmark_passes,
        "benchmark_style_rate": share(benchmark_passes),
    }


def paired_gap(
    first: dict[str, bool], second: dict[str, bool], uids: Iterable[str],
    draws: int = 10_000, seed: int = 7,
) -> dict[str, float]:
    """``first`` minus ``second`` as a share of ``uids``, with a paired
    bootstrap 95% interval: questions are resampled, both sides together."""
    uids = sorted(uids)
    if not uids:
        return {"gap": 0.0, "low": 0.0, "high": 0.0}
    deltas = [int(first.get(u, False)) - int(second.get(u, False)) for u in uids]
    rng = random.Random(seed)
    n = len(deltas)
    draws_sorted = sorted(sum(rng.choices(deltas, k=n)) / n for _ in range(draws))
    return {
        "gap": round(sum(deltas) / n, 4),
        "low": round(draws_sorted[int(0.025 * draws)], 4),
        "high": round(draws_sorted[int(0.975 * draws) - 1], 4),
    }
