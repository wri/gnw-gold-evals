"""Reference planning for the plain baseline — no network."""

import httpx

from goldset.groundtruth import AnalyticsClient
from goldset.plain.reference import (
    GUESSED,
    LIKELY,
    SURE,
    choose_areas,
    fetch,
    links,
    plan,
    source_of,
)
from goldset.store import Case


def _case(**expected) -> Case:
    return Case(id="ch-x", status="ready", group="g", query="q", expected=expected)


def test_sources_read_off_the_id_shape():
    assert source_of("IDN.34.6", {}).source == "gadm"
    assert source_of("BRA1507", {}).source == "landmark"
    assert source_of("BRA1507", {}).certainty == LIKELY
    guess = source_of("555721646", {})
    assert (guess.source, guess.certainty) == ("wdpa", GUESSED)


def test_horizons_recorded_source_beats_a_guess():
    area = source_of("10906", {"10906": "kba"})
    assert (area.source, area.certainty) == ("kba", SURE)


def test_the_surest_alternative_wins():
    """`15913|IDN.34.6`: a bare number is a guess, the GADM code is sure."""
    assert [a.id for a in choose_areas("15913|IDN.34.6")] == ["IDN.34.6"]


def test_equivalent_ids_pick_the_surest_per_area():
    """`/` joins ids for one area; `;` separates the areas compared."""
    areas = choose_areas("555697863/10906;BRA1507", {"10906": "kba"})
    assert [(a.id, a.source) for a in areas] == [("10906", "kba"), ("BRA1507", "landmark")]


def test_ties_keep_case_order():
    assert [a.id for a in choose_areas("BRA|PER")] == ["BRA"]


def test_one_table_per_dataset_and_source():
    reference = plan(_case(aoi_ids="BRA;BRA1507", dataset_id="4;8"), "2026-10-27")
    assert [(t.dataset_id, t.source) for t in reference.tables] == [
        ("4", "gadm"), ("4", "landmark"), ("8", "gadm"), ("8", "landmark"),
    ]
    assert reference.tables[0].payload["aoi"] == {"type": "admin", "ids": ["BRA"]}


def test_an_open_window_ends_on_the_reply_day():
    reference = plan(_case(aoi_ids="BRA", dataset_id="11", start_date="2026-10-01"),
                     "2026-10-27")
    assert reference.tables[0].payload["end_date"] == "2026-10-27"


def test_slu_c_is_skipped_with_its_reason_and_the_rest_kept():
    reference = plan(_case(aoi_ids="CIV", dataset_id="8;9"), "2026-10-27")
    assert [t.dataset_id for t in reference.tables] == ["8"]
    assert "dataset 9" in reference.skipped[0]


def test_no_area_means_no_reference():
    reference = plan(_case(dataset_id="4"), "2026-10-27")
    assert reference.tables == [] and reference.status == "none"


def test_a_failed_table_is_recorded_not_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        if b"BRA1507" in request.content:
            return httpx.Response(422)
        return httpx.Response(200, json={"status": "saved", "data": {"link": "http://a/x/1"}}) \
            if request.method == "POST" else \
            httpx.Response(200, json={"data": {"result": {"area_ha": [1.0]}}})

    reference = plan(_case(aoi_ids="BRA;BRA1507", dataset_id="4"), "2026-10-27")
    fetch([reference], AnalyticsClient("t", transport=httpx.MockTransport(handler)))
    assert links(reference.to_json()) == ["http://a/x/1"]
    assert "422" in reference.tables[1].error
    assert reference.status == "partial"
