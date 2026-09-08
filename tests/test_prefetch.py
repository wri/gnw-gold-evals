"""Prefetch: resolve ground truth before any trial, and fail loudly.

No network — every test drives the client through an httpx.MockTransport.
"""

import httpx
import pytest

from goldset.groundtruth.client import AnalyticsClient, AnalyticsError
from goldset.groundtruth.fetch import digest, is_ground_truth, prefetch
from goldset.groundtruth.request import RequestError
from goldset.store import Case

GT_CASE = Case(
    id="1-046", status="done", group="direct",
    query="How many tonnes of CO2 was emitted in Ihorombe, Madagascar in 2019?",
    expected={
        "aoi_ids": "MDG.3.4_1", "aoi_source": "gadm", "dataset_id": "4",
        "ground_truth": "sum(carbon_emissions_MgCO2e) WHERE tree_cover_loss_year=2019",
        "scope": "analyse",
    },
)

PLAIN_CASE = Case(
    id="1-002", status="done", group="direct", query="Sao Paulo disturbance?",
    expected={"aoi_ids": "BRA.25_1", "aoi_source": "gadm", "dataset_id": "11",
              "answer": "1,299,278 hectares", "scope": "analyse"},
)

RESULT = {
    "aoi_id": ["MDG.3.4", "MDG.3.4"],
    "tree_cover_loss_year": [2018, 2019],
    "area_ha": [1000.0, 1371.15],
    "carbon_emissions_MgCO2e": [500000.0, 658496.56],
}


def _client(handler) -> AnalyticsClient:
    return AnalyticsClient(token="t", transport=httpx.MockTransport(handler))


def _ok(result=RESULT, metadata=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/res-1"}})
        return httpx.Response(
            200, json={"data": {"result": result,
                                "metadata": metadata or {"echo": True}}})
    return handler


def test_resolves_a_ground_truth_case():
    got = prefetch([GT_CASE], _client(_ok()))
    assert list(got) == [GT_CASE.uid]
    gt = got[GT_CASE.uid]
    assert gt.values == pytest.approx([658496.56])
    assert gt.case_id == "1-046"
    assert gt.resource_id == "res-1"
    assert gt.metadata == {"echo": True}
    assert gt.unresolved is None
    assert gt.request.payload["aoi"] == {"type": "admin", "ids": ["MDG.3.4"]}


def test_cases_without_ground_truth_are_skipped_entirely():
    """AC 8 — the mechanism must be invisible to the other 90 cases."""
    assert is_ground_truth(GT_CASE) and not is_ground_truth(PLAIN_CASE)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("a non-ground-truth case must not be fetched")

    assert prefetch([PLAIN_CASE], _client(handler)) == {}


def test_fetch_failure_raises_so_the_run_can_abort():
    """AC 2 — a failed fetch aborts before any trial."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "failed", "message": "boom"})

    with pytest.raises(AnalyticsError, match="job failed"):
        prefetch([GT_CASE], _client(handler))


def test_empty_result_raises():
    """AC 2 — 'returns nothing' is a failure, not an empty expectation."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(
                200, json={"status": "saved", "data": {"link": "http://a/x/1"}})
        return httpx.Response(200, json={"data": {"result": {}}})

    with pytest.raises(AnalyticsError, match="empty result"):
        prefetch([GT_CASE], _client(handler))


def test_unbuildable_case_raises():
    """AC 2 — a case whose request cannot be built aborts rather than guessing."""
    broken = Case(id="x", status="done", group="direct", query="q",
                  expected={"aoi_ids": "RUS", "dataset_id": "4",
                            "ground_truth": "sum(area_ha)"})   # no aoi_source
    with pytest.raises(RequestError, match="no aoi_source"):
        prefetch([broken], _client(_ok()))


def test_missing_metric_is_recorded_not_raised():
    """AC 4 — the fetch worked; this case's metric is absent. That is a row
    error at scoring time, not a reason to kill the whole run."""
    case = Case(id="y", status="done", group="direct", query="q",
                expected={"aoi_ids": "MDG.3.4_1", "aoi_source": "gadm",
                          "dataset_id": "4", "ground_truth": "sum(no_such_column)"})
    got = prefetch([case], _client(_ok()))
    gt = got[case.uid]
    assert gt.unresolved is not None
    assert "not in the response" in gt.unresolved
    assert gt.values == []


def test_digest_moves_with_the_values_and_only_with_them():
    """AC 6 depends on this: the digest is the only thing that tracks a vintage."""
    assert digest([658496.56]) == digest([658496.56])
    assert digest([658496.56]) != digest([658500.0])
    # order-independent, so a reordered multi-value response is not a bump
    assert digest([1.0, 2.0]) == digest([2.0, 1.0])


def test_selected_values_not_the_whole_table_are_hashed():
    """1-046 selects only 2019. A new year landing must NOT move its digest, or
    a genuine agent regression would be excused as a data bump."""
    before = prefetch([GT_CASE], _client(_ok()))[GT_CASE.uid]
    extended = {**RESULT,
                "aoi_id": [*RESULT["aoi_id"], "MDG.3.4"],
                "tree_cover_loss_year": [*RESULT["tree_cover_loss_year"], 2026],
                "area_ha": [*RESULT["area_ha"], 2000.0],
                "carbon_emissions_MgCO2e": [*RESULT["carbon_emissions_MgCO2e"], 900000.0]}
    after = prefetch([GT_CASE], _client(_ok(extended)))[GT_CASE.uid]
    assert before.digest == after.digest

    # ...whereas a case summing every year does move.
    total = Case(id="1-076", status="done", group="direct", query="q",
                 expected={"aoi_ids": "RUS", "aoi_source": "gadm",
                           "dataset_id": "4", "ground_truth": "sum(area_ha)"})
    a = prefetch([total], _client(_ok()))[total.uid]
    b = prefetch([total], _client(_ok(extended)))[total.uid]
    assert a.digest != b.digest


def test_ledger_block_carries_what_an_audit_needs():
    """AC 5 — request, values, digest, resource id, and the server's echo."""
    gt = prefetch([GT_CASE], _client(_ok(metadata={"aoi": {"version": "4.1"}})))
    record = gt[GT_CASE.uid].to_ledger()
    assert set(record) >= {"selector", "values", "digest", "resource_id",
                           "fetched_at", "request", "metadata"}
    assert record["request"]["endpoint"].endswith("/tree_cover_loss/analytics")
    assert record["metadata"] == {"aoi": {"version": "4.1"}}
