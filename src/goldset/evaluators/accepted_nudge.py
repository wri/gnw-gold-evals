"""Accepted-nudge validator: a clarifying choice can be a right answer.

Some questions are fairly answered by asking which dataset or which area is
meant, as long as the choice offered is the right one. AJ decided on
2026-10-26 (BENCHMARK draft-4 review) that such a case passes when the
agent's nudge offers **every** item the case lists; extra options are
allowed. A case opts in per nudge kind:

- ``accept_nudge_offering``: dataset ids a ``dataset_choice`` nudge must offer;
- ``accept_aoi_nudge_offering``: area ids an ``aoi_choice`` nudge must offer
  (ch-quant-188: asking whether Pará means Brazil or Suriname is fine, as
  long as Pará, Brazil is on the list).

A correct direct pull still passes, so the case has two paths and each
attempt is judged on the one it took:

- **nudge path**: the attempt ended in a nudge of an accepted kind and pulled
  no data. ``accepted_nudge_match`` scores the offer, and the checks that
  presuppose a pull (``PULL_PATH_CHECKS`` in ``buckets.py``) are not
  applicable, so the runner skips their evaluators and records ``null``. On
  an ``aoi_choice`` nudge no area is chosen yet, so ``aoi_id_match`` is not
  applicable either.
- **pull path**: anything else. ``accepted_nudge_match`` is ``null`` and the
  usual checks score as before, so a prose ask-back without a nudge still
  fails ``data_pull_exists``.

Items are matched by id from the nudge's ``data`` entries (``dataset_id``,
or ``src_id`` with the GADM suffix dropped, as ``aoi_id_match`` does), never
by option label: labels overlap ("Tree cover loss" is a substring of "Tree
cover loss by dominant driver"), which is why ``nudge_match`` cannot express
this rule.

Opt-in: it fires only on rows that set one of the two fields (``;``-separated
ids, hashed into the uid), so GOLD is unaffected. Fair alternative offers are
separated by ``|`` (``4;8 | 9``): the nudge must cover one of them in full
(draft-5 review, 2026-10-27). Attempts can take different paths, which is
why ``buckets.row_verdict`` judges a row by the majority of its attempt
verdicts (every row since 2026-10-28; these rows first).
"""

from __future__ import annotations

from typing import Any

from goldset.evaluators.guards import _data_was_pulled
from goldset.evaluators.utils import normalize_gadm_id, normalize_value

DATASET_CHOICE = "dataset_choice"
AOI_CHOICE = "aoi_choice"


def _parse_ids(value: Any) -> set[str]:
    if not value:
        return set()
    return {
        normalize_gadm_id(normalize_value(item))
        for item in str(value).split(";")
        if normalize_value(item)
    }


def _parse_offer_sets(value: Any) -> list[set[str]]:
    """Fair offers, separated by ``|``: each is a ``;``-set the nudge must
    cover in full; any one passes (``4;8 | 9``). Without ``|``, one set."""
    if not value:
        return []
    return [ids for part in str(value).split("|") if (ids := _parse_ids(part))]


def _offered_ids(nudge: dict[str, Any]) -> set[str]:
    field = "dataset_id" if nudge.get("type") == DATASET_CHOICE else "src_id"
    return {
        normalize_gadm_id(normalize_value(entry.get(field)))
        for entry in nudge.get("data") or []
        if isinstance(entry, dict) and normalize_value(entry.get(field))
    }


def nudge_path(
    agent_state: dict[str, Any],
    dataset_offering: Any,
    aoi_offering: Any,
) -> str | None:
    """The accepted nudge kind this attempt stopped at with no pull, if any."""
    nudge = agent_state.get("nudge")
    if not isinstance(nudge, dict) or _data_was_pulled(agent_state):
        return None
    accepted = {
        DATASET_CHOICE: bool(_parse_offer_sets(dataset_offering)),
        AOI_CHOICE: bool(_parse_offer_sets(aoi_offering)),
    }
    kind = nudge.get("type")
    return kind if accepted.get(kind) else None


def evaluate_accepted_nudge(
    agent_state: dict[str, Any],
    dataset_offering: Any,
    aoi_offering: Any = "",
) -> dict[str, Any]:
    """Score 1.0 when the nudge offers every item of one listed offer, 0.0
    otherwise.

    ``null`` when the row accepts no nudge of the kind the attempt stopped
    at, and on the pull path (the pull checks speak for it). Also ``null``
    when an accepted nudge carries no ids at all: the harness cannot tell
    what was offered, and an unreadable signal must abstain rather than pass
    or fail (guards.py convention).
    """
    result: dict[str, Any] = {
        "accepted_nudge_match_score": None,
        "actual_nudge_offered": None,
    }
    kind = nudge_path(agent_state, dataset_offering, aoi_offering)
    if kind is None:
        return result

    offered = _offered_ids(agent_state["nudge"])
    if not offered:
        result["actual_nudge_offered"] = f"{kind} nudge carries no ids; abstained"
        return result

    offers = _parse_offer_sets(
        dataset_offering if kind == DATASET_CHOICE else aoi_offering
    )
    result["actual_nudge_offered"] = f"{kind}: " + "; ".join(sorted(offered))
    result["accepted_nudge_match_score"] = (
        1.0 if any(offer <= offered for offer in offers) else 0.0
    )
    return result
