"""Reference tables: the data a right answer to a figure question rests on.

BENCHMARK draft-5 checks Horizon's figures against the table Horizon pulled.
Sonnet pulls nothing, so both assistants are checked against a table this
module fetches from the analytics API, built from the question's own
expectations (area, dataset, layer, parameters, dates). The figure checks
read it exactly as they read a pull: as a statistics entry's ``source_url``.

**As of the reply's day.** A rolling window ("this month's alerts") ends on
the day the reply was given: 27 or 28 October for Horizon's draft-5 replies,
the run day for Sonnet's. The API keys each result by its request, so a
request Horizon already made comes back as Horizon saw it (``polls == 1``);
a new one is computed on today's data, and later alerts can move it.

**Areas.** BENCHMARK writes fair alternatives into ``aoi_ids``: ``|``
between whole alternatives, ``;`` between the areas of one alternative and
``/`` between ids for the same area from different sources
(``555697863/10906/6060`` is Salonga as WDPA, KBA and another id). Cases carry
no ``aoi_source``, so each id's source is read from the id where its shape
says it (GADM codes, LandMark codes), else from the sources Horizon's own
picks recorded, else guessed as WDPA and marked so. The alternative whose
sources are surest is used; ties keep case order.
"""

from __future__ import annotations

import concurrent.futures
import re
from dataclasses import dataclass, field
from typing import Any

from goldset.groundtruth import AnalyticsClient, AnalyticsError, RequestError, build_request
from goldset.store import Case

GADM_ID = re.compile(r"^[A-Z]{3}(\.\d+)*(_\d)?$")
LANDMARK_ID = re.compile(r"^[A-Z]{3}\d+$")
NUMERIC_ID = re.compile(r"^\d+$")

# How sure a source is: read off the id or from Horizon's picks (2), from the
# LandMark code shape (1), or a guess for a bare number (0).
SURE, LIKELY, GUESSED = 2, 1, 0

MAX_WORKERS = 4


@dataclass(frozen=True)
class Area:
    id: str
    source: str  # gadm | wdpa | kba | landmark
    certainty: int


def _split(value: str, sep: str) -> list[str]:
    return [part.strip() for part in value.split(sep) if part.strip()]


def source_of(area_id: str, known: dict[str, str]) -> Area | None:
    """One id's source, or None when nothing says what kind of area it is."""
    bare = re.sub(r"_[1-5]$", "", area_id)
    if GADM_ID.match(area_id):
        return Area(area_id, "gadm", SURE)
    if bare in known:
        return Area(area_id, known[bare], SURE)
    if LANDMARK_ID.match(area_id):
        return Area(area_id, "landmark", LIKELY)
    if NUMERIC_ID.match(area_id):
        return Area(area_id, "wdpa", GUESSED)
    return None


def choose_areas(aoi_ids: str, known: dict[str, str] | None = None) -> list[Area]:
    """The areas to fetch for ``aoi_ids``: the surest alternative, and for
    each of its areas the surest id. Empty when no id can be placed."""
    known = known or {}
    best: list[Area] = []
    best_score = -1
    for alternative in _split(aoi_ids or "", "|"):
        areas = []
        for area in _split(alternative, ";"):
            candidates = [a for i in _split(area, "/") if (a := source_of(i, known))]
            if not candidates:
                areas = []
                break
            areas.append(max(candidates, key=lambda a: a.certainty))
        if not areas:
            continue
        score = min(a.certainty for a in areas)
        if score > best_score:
            best, best_score = areas, score
    return best


@dataclass
class Table:
    dataset_id: str
    source: str
    aoi_ids: list[str]
    endpoint: str
    payload: dict[str, Any]
    link: str = ""
    polls: int = 0
    error: str = ""


@dataclass
class Reference:
    """Every table one question's figures can be checked against."""

    uid: str
    id: str
    as_of: str
    areas: list[dict[str, Any]] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def links(self) -> list[str]:
        return [t.link for t in self.tables if t.link]

    @property
    def status(self) -> str:
        if not self.links:
            return "none"
        return "ok" if not self.skipped and all(t.link for t in self.tables) else "partial"

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id, "as_of": self.as_of, "status": self.status,
            "areas": self.areas,
            "tables": [t.__dict__ for t in self.tables],
            "skipped": self.skipped,
        }

    @classmethod
    def from_json(cls, uid: str, data: dict[str, Any]) -> Reference:
        return cls(
            uid=uid, id=data["id"], as_of=data["as_of"], areas=data.get("areas", []),
            tables=[Table(**t) for t in data.get("tables", [])],
            skipped=list(data.get("skipped", [])),
        )


def plan(case: Case, as_of: str, known: dict[str, str] | None = None,
         areas_override: dict[str, str] | None = None) -> Reference:
    """The requests a resolved case implies, not yet fetched.

    ``areas_override`` (from the overlay) pins an id's source when the guess
    is wrong. A dataset the builder cannot request (sLUC) is skipped with its
    reason, and the question's figures go unchecked against it.
    """
    reference = Reference(uid=case.uid, id=case.id, as_of=as_of)
    expected = dict(case.expected)
    areas = choose_areas(expected.get("aoi_ids", ""), {**(known or {}), **(areas_override or {})})
    if not areas:
        reference.skipped.append(f"no area could be placed from {expected.get('aoi_ids')!r}")
        return reference
    reference.areas = [a.__dict__ for a in areas]
    by_source: dict[str, list[str]] = {}
    for area in areas:
        by_source.setdefault(area.source, []).append(area.id)
    for dataset_id in _split(re.sub(r"\|", ";", expected.get("dataset_id", "")), ";"):
        for source, ids in by_source.items():
            one = Case(id=case.id, status=case.status, group=case.group, set=case.set,
                       query=case.query, notes=case.notes,
                       expected={**expected, "aoi_ids": ";".join(ids), "aoi_source": source})
            try:
                request = build_request(one, dataset_id=dataset_id, today=as_of)
            except RequestError as error:
                reference.skipped.append(f"dataset {dataset_id}: {error}")
                continue
            reference.tables.append(Table(dataset_id, source, ids, request.endpoint,
                                          request.payload))
    if not reference.tables and not reference.skipped:
        reference.skipped.append("no dataset_id")
    return reference


def fetch(references: list[Reference], client: AnalyticsClient,
          max_workers: int = MAX_WORKERS) -> None:
    """Fill each planned table's link, or its error. A failed table is
    recorded, never raised: one bad request must not lose the others."""
    tables = [t for r in references for t in r.tables if not t.link]

    def one(table: Table) -> None:
        try:
            result = client.fetch(table.endpoint, table.payload)
        except AnalyticsError as error:
            table.error = str(error)[:300]
            return
        table.link, table.polls = result.link, result.polls

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(one, tables))


def resource_id(link: str) -> str:
    return link.rstrip("/").split("/")[-1]
