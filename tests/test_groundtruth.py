"""Request builder and analytics client, ported from ``main`` — no network.

The reference row is **1-046** ("How many tonnes of CO2 was emitted in Ihorombe,
Madagascar in 2019 due to tree cover loss?"): it exercises the GADM suffix
strip and a year that the request leaves to the figure formula. The selector
and the runner's pull re-read are not on this branch, so their tests stay on
``main``.
"""

import json
from pathlib import Path

import httpx
import pytest

from goldset.groundtruth.catalog import dataset_for, datasets
from goldset.groundtruth.client import (
    AnalyticsClient,
    AnalyticsError,
    analytics_headers,
)
from goldset.groundtruth.request import RequestError, build_request, canopy_cover
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
    table = datasets()
    assert (table["4"].endpoint == table["8"].endpoint == table["10"].endpoint)
    assert table["4"].intersections == ()
    assert table["8"].intersections == ("driver",)
    assert table["10"].intersections == ("fire",)


def test_the_request_table_is_built_from_the_committed_snapshot():
    """Endpoint/window/fixed come from cases/zeno_catalog.json, so an upstream
    window extension cannot silently leave the builder computing the old one."""
    snapshot = json.loads(
        (Path(__file__).resolve().parents[1] / "cases" / "zeno_catalog.json")
        .read_text(encoding="utf-8")
    )
    entries = {e["dataset_id"]: e for e in snapshot["datasets"]}
    for dataset_id, dataset in datasets().items():
        entry = entries[dataset_id]
        assert dataset.endpoint == entry["analytics_api_endpoint"]
        assert dataset.start_date == entry["start_date"]
        assert dataset.end_date == entry["end_date"]
        assert dataset.fixed == entry["content_date_fixed"]


def test_dist_alert_is_retired_not_stale():
    """zeno deleted dataset 0's catalog entry, so it is absent from the snapshot
    and the builder refuses it. A hardcoded fallback would have kept issuing
    requests for a dataset the agent can no longer select."""
    assert dataset_for("0") is None
    case = Case(id="d0", status="done", group="direct", query="q",
                expected={"aoi_ids": "BRA.25_1", "aoi_source": "gadm",
                          "dataset_id": "0", "ground_truth": "sum(area_ha)"})
    with pytest.raises(RequestError, match="unknown dataset_id '0'"):
        build_request(case)


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


def test_ground_truth_requests_stay_on_production():
    """Ground truth is the published data whichever deployment a run targets."""
    assert analytics_headers("tok")["X-environment"] == "production"


def _layer_case(dataset_id: str, layer: str) -> Case:
    return Case(
        id=f"x-{dataset_id}", status="done", group="direct", query="q",
        expected={"aoi_ids": "MDG.3.4_1", "aoi_source": "gadm",
                  "dataset_id": dataset_id, "context_layer": layer,
                  "ground_truth": "sum(area_ha)"},
    )


@pytest.mark.parametrize("dataset_id", ["4", "8", "10"])
@pytest.mark.parametrize("layer", ["primary_forest", "intact_forest"])
def test_the_loss_family_takes_either_forest_layer(dataset_id, layer):
    request = build_request(_layer_case(dataset_id, layer))
    assert request.payload["forest_filter"] == layer


@pytest.mark.parametrize("dataset_id", ["5", "7"])
def test_gain_and_extent_take_primary_forest_only(dataset_id):
    """Only the tree-cover-loss datasets have an `intact_forest` filter. Tree
    cover gain and tree cover do not, so the request sends null for it, as the
    agent does."""
    assert build_request(
        _layer_case(dataset_id, "primary_forest")
    ).payload["forest_filter"] == "primary_forest"
    assert build_request(
        _layer_case(dataset_id, "intact_forest")
    ).payload["forest_filter"] is None


@pytest.mark.parametrize("dataset_id", ["4", "5", "7", "8", "10"])
def test_a_layer_that_is_not_a_forest_filter_is_dropped(dataset_id):
    """`context_layer` is not `forest_filter`. A layer that is not a forest
    filter is sent as null, which is what the agent sends."""
    assert build_request(
        _layer_case(dataset_id, "natural_lands")
    ).payload["forest_filter"] is None


@pytest.mark.parametrize("layer", [None, "natural_lands"])
def test_integrated_alerts_payload_is_dates_only(layer):
    """Integrated Alerts takes the AOI and full dates only. The API rejects
    unknown fields with a 422, including an empty `intersections` list, and
    zeno sends no context layer for this dataset, so neither may appear."""
    expected = {"aoi_ids": "BRA.25_1", "aoi_source": "gadm", "dataset_id": "11",
                "start_date": "2024-07-01", "end_date": "2024-12-31",
                "ground_truth": "sum(area_ha)"}
    if layer:
        expected["context_layer"] = layer
    case = Case(id="1-002", status="done", group="direct", query="q", expected=expected)
    request = build_request(case)
    assert request.endpoint == "/v0/land_change/integrated_alerts/analytics"
    assert request.payload == {
        "aoi": {"type": "admin", "ids": ["BRA.25"]},
        "start_date": "2024-07-01",
        "end_date": "2024-12-31",
    }


def test_dataset_alternatives_select_one_payload():
    """`dataset_id: "8;10"` names two defensible routings (cases/README.md,
    1-062). 8 and 10 share an endpoint, so the alternative shows up in the
    intersections rather than the URL — which is the trap the split exists for."""
    case = Case(id="z", status="done", group="direct", query="q",
                expected={"aoi_ids": "BRA.25_1", "aoi_source": "gadm",
                          "dataset_id": "8;10", "ground_truth": "sum(area_ha)"})
    first = build_request(case)
    assert first.endpoint.endswith("/tree_cover_loss/analytics")
    assert first.payload["intersections"] == ["driver"]
    other = build_request(case, dataset_id="10")
    assert other.endpoint == first.endpoint
    assert other.payload["intersections"] == ["fire"]


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
    assert result.polls == 2             # pending first: computed on request
    assert sum(result.result["area_ha"]) == pytest.approx(3271.15)


def test_client_raises_on_failed_job():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "failed", "message": "nope"})

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="job failed"):
        client.fetch("/v0/x/analytics", {})


def test_client_raises_on_empty_result():
    """An empty payload aborts rather than becoming an empty expectation."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/1"}})
        return httpx.Response(200, json={"data": {"result": {}}})

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="empty result"):
        client.fetch("/v0/x/analytics", {})


def _saved_then(second: httpx.Response):
    """POST resolves immediately; the result-link GET returns `second`."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/1"}})
        return second
    return handler


@pytest.mark.parametrize(
    "response, expected",
    [
        (httpx.Response(404), "404"),
        (httpx.Response(500), "500"),
        (httpx.Response(200, text="<html>gateway</html>"), "malformed JSON"),
    ],
)
def test_a_bad_result_link_is_an_analytics_error_not_a_traceback(response, expected):
    """The result link is a cache entry we do not control, so it can 404 or
    serve HTML. prefetch catches only AnalyticsError: anything else escapes the
    ABORT path as a raw traceback."""
    client = AnalyticsClient(
        token="t", transport=httpx.MockTransport(_saved_then(response)))
    with pytest.raises(AnalyticsError, match=expected):
        client.fetch("/v0/x/analytics", {})


def test_a_non_json_post_response_is_an_analytics_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="upstream timeout")

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="malformed JSON"):
        client.fetch("/v0/x/analytics", {})


def test_a_transport_failure_on_the_get_hop_is_an_analytics_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/1"}})
        raise httpx.ConnectError("link host unreachable")

    client = AnalyticsClient(token="t", transport=httpx.MockTransport(handler))
    with pytest.raises(AnalyticsError, match="unreachable"):
        client.fetch("/v0/x/analytics", {})


def test_a_result_already_stored_comes_back_on_the_first_poll():
    """The API keys results by request, so one already asked for is served
    as first computed: that is how a rescore reads what an assistant saw."""
    client = AnalyticsClient(
        token="t",
        transport=httpx.MockTransport(_saved_then(
            httpx.Response(200, json={"data": {"result": {"area_ha": [1.0]}}})
        )),
    )
    assert client.fetch("/v0/x/analytics", {}).polls == 1


def test_an_open_window_ends_on_the_day_given():
    """A rescore builds the request as of the reply's day, not today's."""
    case = Case(id="a", status="done", group="direct", query="q",
                expected={"aoi_ids": "BRA.25_1", "aoi_source": "gadm",
                          "dataset_id": "11", "start_date": "2026-10-01"})
    request = build_request(case, today="2026-10-27")
    assert request.payload["end_date"] == "2026-10-27"
