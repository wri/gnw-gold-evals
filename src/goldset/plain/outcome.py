"""Attempts and questions to outcomes: right, wrong, declined or uncovered.

An attempt's outcome combines its reply checks with its decline label:

- no reply (Horizon's timeouts, Sonnet's $1 stop): wrong, as BENCHMARK
  counts it;
- asked back: right when it offers every accepted choice (the accepted-nudge
  check for Horizon, the offer judge for Sonnet), else as a decline;
- declined: right only where the overlay says a decline is the right answer
  and the checks pass, else declined;
- answered: right when every scored gating check passed, wrong when one
  failed, uncovered when none scored.

A question takes right when most of its scored attempts are right (ties
fail, as in BENCHMARK); otherwise declined or wrong, whichever is commoner,
a tie counting as wrong; uncovered when no attempt scored. Beside it rides
the BENCHMARK-style verdict, which ignores the label, so the extra outcomes
hide nothing.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

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
    verdict = checks_verdict(attempt.get("checks") or {}, calls)
    if label in ("declined", "asked_back"):
        # Where a decline is the right answer, only a failed check (say, an
        # invented figure alongside it) stops it counting.
        return "right" if calls.decline_right and verdict != "fail" else "declined"
    if verdict is None:
        return "uncovered"
    return "right" if verdict == "pass" else "wrong"


def benchmark_style(attempt: dict[str, Any], calls: Calls) -> str | None:
    """pass | fail | None by BENCHMARK's rule: the checks alone, no label.
    An offer stands in for the accepted-nudge path."""
    if attempt.get("no_answer"):
        return "fail"
    if attempt.get("error"):
        return None
    if attempt.get("offer") is not None:
        return "pass" if attempt["offer"] == 1.0 else "fail"
    return checks_verdict(attempt.get("checks") or {}, calls)


def wrong_figure(attempt: dict[str, Any], calls: Calls) -> bool:
    """An answer whose figure check failed: the clearest way to mislead."""
    return (
        attempt.get("label") == "answered"
        and "figure_match" in gating(calls)
        and (attempt.get("checks") or {}).get("figure_match") == 0.0
    )


@dataclass(frozen=True)
class QuestionResult:
    outcome: str  # right | wrong | declined | uncovered
    benchmark: str  # pass | fail | uncovered
    wrong_figure: bool
    attempts: tuple[str | None, ...]


def question(attempts: list[dict[str, Any]], calls: Calls) -> QuestionResult:
    outcomes = [attempt_outcome(a, calls) for a in attempts]
    scored = [o for o in outcomes if o in ("right", "wrong", "declined")]
    if not scored:
        outcome = "uncovered"
    elif outcomes.count("right") * 2 > len(scored):
        outcome = "right"
    else:
        outcome = "declined" if outcomes.count("declined") > outcomes.count("wrong") else "wrong"

    verdicts = [v for a in attempts if (v := benchmark_style(a, calls)) is not None]
    if not verdicts:
        benchmark = "uncovered"
    else:
        benchmark = "pass" if verdicts.count("pass") * 2 > len(verdicts) else "fail"

    figure_wrong = sum(wrong_figure(a, calls) for a in attempts)
    return QuestionResult(outcome, benchmark, bool(scored) and figure_wrong * 2 > len(scored),
                          tuple(outcomes))


def summarise(results: dict[str, QuestionResult]) -> dict[str, Any]:
    """Counts and shares over every question, uncovered included."""
    total = len(results)
    counts = Counter(r.outcome for r in results.values())
    share = (lambda n: round(n / total, 4)) if total else (lambda n: 0.0)
    return {
        "questions": total,
        **{o: counts.get(o, 0) for o in OUTCOMES},
        "rates": {o: share(counts.get(o, 0)) for o in OUTCOMES},
        "wrong_figure": sum(r.wrong_figure for r in results.values()),
        "wrong_figure_rate": share(sum(r.wrong_figure for r in results.values())),
        "benchmark_style_pass": sum(r.benchmark == "pass" for r in results.values()),
        "benchmark_style_rate": share(sum(r.benchmark == "pass" for r in results.values())),
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
