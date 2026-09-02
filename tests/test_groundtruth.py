"""Request builder, selector, and analytics client — no network.

The reference row is **1-046** ("How many tonnes of CO2 was emitted in Ihorombe,
Madagascar in 2019 due to tree cover loss?"), because it exercises three things
at once: the GADM suffix strip, a metric that is not the obvious column, and a
year that lives in the selector rather than the request.
"""

import httpx
import pytest

from goldset.groundtruth.catalog import DATASETS
from goldset.groundtruth.client import AnalyticsClient, AnalyticsError
from goldset.groundtruth.request import RequestError, build_request, canopy_cover
from goldset.groundtruth.selector import (
    SelectorError,
    apply_selector,
    parse_selector,
)
from goldset.store import Case

CASE_1046 = Case(
    id="1-046",
    status="done",
    group="direct",
    query="How many tonnes of CO2 was emitted in Ihorombe, Madagascar in 2019 "
          "due to tree cover loss?",
    expected={
        "aoi_ids": "MDG.3.4_1",
        "aoi_source": "gadm",
        "dataset_id": "4",
        "dataset_name": "Forest GHG emissions",
        "ground_truth": "sum(carbon_emissions_MgCO2e) WHERE tree_cover_loss_year=2019",
        "scope": "analyse",
    },
)

# Column-oriented, exactly as the API answers.
RESULT = {
    "aoi_id": ["MDG.3.4", "MDG.3.4", "MDG.3.4"],
    "aoi_type": ["admin", "admin", "admin"],
    "tree_cover_loss_year": [2018, 2019, 2020],
    "area_ha": [1000.0, 1371.15, 900.0],
    "carbon_emissions_MgCO2e": [500000.0, 658496.56, 480000.0],
}


def test_1046_payload_matches_what_the_agent_sent():
    request = build_request(CASE_1046)
    assert request.endpoint == "/v0/land_change/tree_cover_loss/analytics"
    assert request.payload == {
        # MDG.3.4_1 -> MDG.3.4: the API rejects the admin-level suffix
        "aoi": {"type": "admin", "ids": ["MDG.3.4"]},
        # no dates on the case (annual dataset) -> the catalog's own window
        "start_year": "2001",
        "end_year": "2025",
        "forest_filter": None,
        "intersections": [],
        "canopy_cover": 30,
    }


def test_selector_picks_the_year_the_request_could_not():
    selector = parse_selector(CASE_1046.expected["ground_truth"])
    assert selector.aggregate == "sum"
    assert selector.column == "carbon_emissions_MgCO2e"
    assert selector.filter_column == "tree_cover_loss_year"
    assert apply_selector(selector, RESULT) == pytest.approx(658496.56)


def test_where_is_case_insensitive_but_canonicalises():
    """The selector is hashed into the uid, so `where` and `WHERE` must not
    mint two uids for the same test."""
    lower = parse_selector("sum(area_ha) where tree_cover_loss_year=2019")
    upper = parse_selector("SUM(area_ha) WHERE tree_cover_loss_year=2019")
    assert lower == upper
    assert lower.canonical() == "sum(area_ha) WHERE tree_cover_loss_year=2019"


def test_bare_column_is_refused():
    """An explicit aggregate is mandatory: 1-059 pulls 254 AOIs, so an implicit
    reduction over a multi-row match would be silently wrong."""
    with pytest.raises(SelectorError):
        parse_selector("carbon_emissions_MgCO2e WHERE tree_cover_loss_year=2019")


def test_missing_metric_errors_rather_than_passing_vacuously():
    """AC #4 — the fetched data lacks the metric the case needs."""
    with pytest.raises(SelectorError, match="not in the response"):
        apply_selector(parse_selector("sum(nonexistent_column)"), RESULT)
    with pytest.raises(SelectorError, match="no rows where"):
        apply_selector(
            parse_selector("sum(area_ha) WHERE tree_cover_loss_year=1999"), RESULT
        )


def test_gadm_suffix_stripped_only_for_gadm():
    """KBA/WDPA/landmark ids are opaque and must pass through untouched."""
    kba = Case(id="k", status="done", group="direct", query="q",
               expected={"aoi_ids": "15060", "aoi_source": "kba",
                         "dataset_id": "3", "ground_truth": "sum(area_ha)"})
    assert build_request(kba).payload["aoi"] == {
        "type": "key_biodiversity_area", "ids": ["15060"]
    }


def test_landmark_spelling_is_normalised():
    """The case set spells it both `Landmark` (5) and `landmark` (2)."""
    for spelling in ("Landmark", "landmark"):
        case = Case(id="l", status="done", group="direct", query="q",
                    expected={"aoi_ids": "MEX9713", "aoi_source": spelling,
                              "dataset_id": "3", "ground_truth": "sum(area_ha)"})
        assert build_request(case).payload["aoi"]["type"] == "indigenous_land"


def test_datasets_4_8_10_share_an_endpoint_but_differ_by_intersections():
    assert (DATASETS["4"].endpoint == DATASETS["8"].endpoint
            == DATASETS["10"].endpoint)
    assert DATASETS["4"].intersections == ()
    assert DATASETS["8"].intersections == ("driver",)
    assert DATASETS["10"].intersections == ("fire",)


def test_missing_aoi_fields_abort_loudly():
    """17 v2 cases lack aoi_source and 7 numeric ones lack aoi_ids; neither may
    be inferred, because that would redo the agent's own AOI resolution."""
    no_source = Case(id="x", status="done", group="direct", query="q",
                     expected={"aoi_ids": "RUS", "dataset_id": "4",
                               "ground_truth": "sum(area_ha)"})
    with pytest.raises(RequestError, match="no aoi_source"):
        build_request(no_source)

    no_ids = Case(id="y", status="done", group="direct", query="q",
                  expected={"aoi_source": "wdpa", "dataset_id": "4",
                            "ground_truth": "sum(area_ha)"})
    with pytest.raises(RequestError, match="no aoi_ids"):
        build_request(no_ids)


def test_canopy_cover_defaults_and_pins():
    assert canopy_cover({}) == 30
    assert canopy_cover(
        {"dataset_parameters": '[{"name": "canopy_cover", "values": [50]}]'}
    ) == 50


def test_dataset_alternatives_select_one_endpoint():
    """`dataset_id: "0;11"` names two defensible routings (cases/README.md)."""
    case = Case(id="z", status="done", group="direct", query="q",
                expected={"aoi_ids": "BRA.25_1", "aoi_source": "gadm",
                          "dataset_id": "0;11", "start_date": "2024-07-01",
                          "end_date": "2024-12-31", "ground_truth": "sum(area_ha)"})
    assert build_request(case).endpoint.endswith("/dist_alerts/analytics")
    other = build_request(case, dataset_id="11")
    assert other.endpoint.endswith("/integrated_alerts/analytics")
    assert other.payload["start_date"] == "2024-07-01"


# --------------------------------------------------------------------------
# client: the two-hop protocol, against a mock transport


def test_client_polls_then_fetches():
    calls = {"post": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            calls["post"] += 1
            if calls["post"] == 1:
                return httpx.Response(200, json={"status": "pending", "data": {}},
                                      headers={"Retry-After": "0"})
            return httpx.Response(
                200, json={"status": "saved",
                           "data": {"link": "http://a/analytics/abc"}})
        return httpx.Response(
            200, json={"data": {"result": RESULT, "metadata": {"echo": 1}}})

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    result = client.fetch("/v0/x/analytics", {"aoi": {}})
    assert calls["post"] == 2            # re-POSTed the identical payload
    assert result.resource_id == "abc"
    assert result.metadata == {"echo": 1}
    assert apply_selector(
        parse_selector("sum(area_ha)"), result.result
    ) == pytest.approx(3271.15)


def test_client_raises_on_failed_job():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "failed", "message": "nope"})

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="job failed"):
        client.fetch("/v0/x/analytics", {})


def test_client_raises_on_empty_result():
    """AC #2 - an empty payload aborts rather than becoming an empty expectation."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/1"}})
        return httpx.Response(200, json={"data": {"result": {}}})

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="empty result"):
        client.fetch("/v0/x/analytics", {})
