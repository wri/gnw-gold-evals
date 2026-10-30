"""One attempt through the reply checks, for either assistant.

The four reply checks run through the harness's own registry entries, so
their prompts, parsing and 2% rule are BENCHMARK's. The attempt state they
read holds only what the user reads (the reply, plus a nudge's options) and,
in place of a pull, the reference tables as statistics entries: the figure
checks fetch a ``source_url`` either way.

Horizon's attempts that stopped at an accepted nudge are judged as BENCHMARK
judges them, by the ids the nudge offered (``accepted_nudge_match``), with
the reply checks not applicable. Sonnet has no nudge, so a prose ask-back is
read by the offer judge against the same accepted ids.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from goldset.adapter import case_to_expected
from goldset.evaluators.accepted_nudge import evaluate_accepted_nudge, nudge_path
from goldset.plain import judges
from goldset.plain.outcome import GATING
from goldset.registry import EVALUATORS
from goldset.store import Case

REPLY_EVALUATORS = tuple(s for s in EVALUATORS
                         if s.name in ("answer", "figures", "figure_claim", "answer_period"))


def as_read(text: str, nudge: dict[str, Any] | None = None) -> str:
    """The reply as the user reads it: a nudge's options show as buttons."""
    options = [str(o) for o in (nudge or {}).get("options") or []]
    if not options:
        return text
    return f"{text}\n\n[Options offered as buttons: {'; '.join(options)}]"


def horizon_nudge_offer(case: Case, nudge: dict[str, Any] | None,
                        pulled_links: list[str]) -> float | None:
    """accepted_nudge_match on Horizon's own state, or None off that path.

    Read on what Horizon itself pulled, not the reference: the path is
    "stopped at an accepted nudge without pulling".
    """
    state = {"nudge": nudge, "statistics": [{"source_url": u} for u in pulled_links]}
    offering = case.expected.get("accept_nudge_offering", "")
    aoi_offering = case.expected.get("accept_aoi_nudge_offering", "")
    if nudge_path(state, offering, aoi_offering) is None:
        return None
    return evaluate_accepted_nudge(state, offering, aoi_offering)["accepted_nudge_match_score"]


def offer_options(case: Case, dataset_names: dict[str, str],
                  area_names: dict[str, str]) -> list[list[str]]:
    """Each fair offer as names a judge can find in prose (``|`` separates
    fair offers; any one, in full, passes)."""
    offers = []
    for field, names in (("accept_nudge_offering", dataset_names),
                         ("accept_aoi_nudge_offering", area_names)):
        for part in str(case.expected.get(field) or "").split("|"):
            ids = [i.strip() for i in part.split(";") if i.strip()]
            if ids:
                offers.append([names.get(i, i) for i in ids])
    return offers


def run_checks(case: Case, text: str, links: list[str]) -> dict[str, Any]:
    """The four reply checks on ``text``, figures against ``links``."""
    state = {
        "messages": [SimpleNamespace(content=text)],
        "statistics": [{"source_url": link} for link in links],
    }
    expected = case_to_expected(case)
    merged: dict[str, Any] = {}
    for spec in REPLY_EVALUATORS:
        merged.update(spec.run(state, expected, case.query, None))
    checks = {name: merged.get(f"{name}_score") for name in GATING}
    reasons = {name: merged.get(f"{name}_reason") or merged.get(f"{name}_score_reason")
               for name in GATING}
    reasons["figure_match"] = merged.get("figure_match_reason")
    errors = [e for e in merged.get("judge_errors") or []]
    return {"checks": checks, "reasons": reasons, "judge_errors": errors}


def score_attempt(
    case: Case,
    text: str,
    links: list[str],
    *,
    nudge_offer: float | None = None,
    offers: list[list[str]] | None = None,
) -> dict[str, Any]:
    """One attempt: its label, its checks, and any offer it made.

    ``case`` is resolved to the reply's day. ``nudge_offer`` is Horizon's
    accepted-nudge score when it took that path; ``offers`` are the fair
    offers Sonnet's prose is read against.
    """
    if not text.strip():
        return {"no_answer": True}
    if nudge_offer is not None:
        return {"label": "asked_back", "label_reason": "stopped at an accepted nudge",
                "offer": nudge_offer, "checks": {}, "reasons": {}}
    try:
        labelled = judges.label(case.query, text)
    except Exception as error:  # judge outage: an error, never a verdict
        return {"error": f"label judge: {error}"}
    scored = run_checks(case, text, links)
    attempt: dict[str, Any] = {
        "label": labelled["label"], "label_reason": labelled["reason"],
        "checks": scored["checks"], "reasons": scored["reasons"], "offer": None,
    }
    if scored["judge_errors"]:
        attempt["error"] = f"judge errors: {scored['judge_errors']}"
    if labelled["label"] == "asked_back" and offers:
        try:
            judged = [judges.offers(case.query, text, options) for options in offers]
        except Exception as error:
            attempt["error"] = f"offer judge: {error}"
            return attempt
        attempt["offer"] = 1.0 if any(j["offers_all"] for j in judged) else 0.0
        attempt["offer_reason"] = "; ".join(str(j["reason"]) for j in judged)
    return attempt
