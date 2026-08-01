"""Deterministic guards: cheap checks against the failure modes the ported
suite is blind to (PR-04 G1-G4 + F2).

Reference failures, all from the 2026-07-31 staging run:

- 1-030 pulled no data, selected no dataset, and answered confidently from
  web knowledge (citing wri.org) — scored ``agent_answer`` 1.0.
- 1-004 / 1-008 / 1-030 / 1-055 answered in prose with no chart at all —
  the chart check returned None instead of failing.

Every guard is tri-state: ``None`` means "not applicable to this case",
never "could not tell" — where a signal is unreadable the guard abstains
with an ``actual_*`` explanation, following the chart_numeric convention.
Scores read as "1.0 = clean, 0.0 = violated".
"""

from __future__ import annotations

import re
from typing import Any

from goldset.evaluators.answer_evaluator import extract_final_answer_text
from goldset.evaluators.utils import normalize_value

# Substantive prose (vs a bare refusal/greeting): anything this long that
# arrives with no data behind it is an answer the user will believe.
SUBSTANTIVE_ANSWER_CHARS = 80

# Links to the product itself are not web fallback.
_OWN_DOMAINS = ("globalnaturewatch.org",)
_LINK_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def _last_statistics(agent_state: dict[str, Any]) -> dict[str, Any] | None:
    statistics = agent_state.get("statistics")
    if isinstance(statistics, list):
        statistics = statistics[-1] if statistics else None
    return statistics if isinstance(statistics, dict) else None


def _data_was_pulled(agent_state: dict[str, Any]) -> bool:
    statistics = _last_statistics(agent_state)
    if not statistics:
        return False
    if str(statistics.get("source_url") or "") or str(statistics.get("id") or ""):
        return True
    data = statistics.get("data")
    return bool(data)


def _pull_dataset_reference(statistics: dict[str, Any]) -> str:
    """The pull's explicit dataset registry id, ``""`` when the entry has none.

    Real statistics entries carry ``dataset_id`` (int-typed) alongside
    ``source_url``/``id``/``data``/``start_date``/``end_date`` — pinned from 84
    live pull-bearing artifacts (81/84 carried it; see
    results/campaigns/20260801-pr08.md, "Step 4 — G4 pinned"). Presence is
    checked by key, not truthiness: dataset id ``0`` is a real registry id.
    """
    if "dataset_id" in statistics:
        return normalize_value(statistics.get("dataset_id"))
    return ""


def evaluate_guards(
    agent_state: dict[str, Any],
    expects_data_pull: bool,
    expected_answer: str,
    expected_dataset_id: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "chart_produced_score": None,
        "answered_without_data_score": None,
        "web_fallback_score": None,
        "pull_source_match_score": None,
        "actual_web_links": None,
        "actual_pull_source": None,
    }

    answer_text = extract_final_answer_text(agent_state.get("messages", []))
    charts = agent_state.get("charts_data") or []
    pulled = _data_was_pulled(agent_state)
    dataset = agent_state.get("dataset") or {}
    dataset_selected = bool(normalize_value(dataset.get("dataset_id")))

    # F2 — chart_produced: a row whose expected_answer implies a chart must
    # produce one. Previously "no chart" made charts_answer vanish to None.
    # Gated on expects_data_pull like every sibling guard, so a clarification
    # row (expected_clarification=True) is exempt even with an answer set.
    if expected_answer and expects_data_pull:
        result["chart_produced_score"] = 1.0 if charts else 0.0

    # G1 — answered_without_data: catches 1-030 exactly. Violation is a
    # substantive answer with no pull AND no dataset selection behind it.
    if expects_data_pull:
        answered = len(answer_text.strip()) >= SUBSTANTIVE_ANSWER_CHARS
        violated = answered and not pulled and not dataset_selected
        result["answered_without_data_score"] = 0.0 if violated else 1.0

    # G2 — web_fallback: external citations in a data-pull answer signal the
    # answer came from web knowledge, not the pulled data.
    if expects_data_pull and answer_text:
        links = [
            link
            for link in _LINK_RE.findall(answer_text)
            if not any(domain in link.lower() for domain in _OWN_DOMAINS)
        ]
        result["web_fallback_score"] = 0.0 if links else 1.0
        if links:
            result["actual_web_links"] = "; ".join(sorted(set(links))[:5])

    # G4 — pull_source_match: the pull must reference the expected dataset.
    # Compared as exact equality on the entry's explicit ``dataset_id`` key,
    # which cannot false-positive. ``source_url``/``id`` are deliberately NOT
    # compared: real source_urls reference datasets by slug
    # (``/v0/land_change/<slug>/analytics``), never by registry id, so with
    # short numeric expected ids ("0"–"11") a token match against the URL
    # would false-positive on date/query fragments ("11" is also a month in
    # ``start_date=2024-11-01``) and a non-match would false-negative every
    # correct slug URL. When the entry lacks ``dataset_id`` (3/84 observed),
    # the guard abstains with the source_url/id it saw, so abstentions are
    # auditable rather than silent.
    if expected_dataset_id and pulled:
        statistics = _last_statistics(agent_state) or {}
        reference = _pull_dataset_reference(statistics)
        if not reference:
            source_url = normalize_value(statistics.get("source_url")) or "none"
            pull_id = normalize_value(statistics.get("id")) or "none"
            result["actual_pull_source"] = (
                "statistics entry carries no dataset_id "
                f"(source_url={source_url}, id={pull_id}); guard abstained"
            )
        else:
            result["actual_pull_source"] = reference
            expected = normalize_value(expected_dataset_id)
            result["pull_source_match_score"] = 1.0 if reference == expected else 0.0

    return result
