"""End-to-end runner test against a mocked API — no network, no judge.

Covers: streamed chat POST, trace capture, state fetch, evaluation via the
registry, artifact capture, and the CLI's result->ledger-entry mapping.
"""

import gzip
import json

import httpx
import pytest

from goldset.adapter import case_to_expected
from goldset.cli import merge_trials, result_to_entry
from goldset.runner.api import APITestRunner
from goldset.store import Case

CASE = Case(
    id="1-002",
    status="done",
    group="direct",
    query="Sao Paulo disturbance in H2 2024?",
    expected={"aoi_ids": "BRA.25_1", "dataset_id": "11"},
)

STATE = {
    "aoi_selection": {
        "aois": [{"src_id": "BRA.25_1", "name": "São Paulo",
                  "subtype": "state-province", "source": "gadm"}]
    },
    "dataset": {"dataset_id": "11", "dataset_name": "Integrated alerts",
                "parameters": [], "context_layer": None},
    "messages": [],
    "charts_data": [],
    "codeact_parts": [],
    "statistics": [{"source_url": "https://api.example/x", "id": "pull-1",
                    "data": [{"year": 2024, "area_ha": 1.0}],
                    "start_date": "2024-07-01", "end_date": "2024-12-31"}],
}


def transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            lines = [
                json.dumps({"node": "trace_info",
                            "update": json.dumps({"trace_id": "t-1",
                                                  "trace_url": "https://lf/t-1"})}),
                json.dumps({"node": "agent", "update": "{}"}),
            ]
            return httpx.Response(200, text="\n".join(lines))
        if request.url.path.startswith("/api/threads/"):
            # the real endpoint returns state as a serialised JSON string
            return httpx.Response(200, json={"state": json.dumps(STATE)})
        raise AssertionError(f"unexpected request: {request.url}")

    return httpx.MockTransport(handler)


@pytest.fixture
def patched_client(monkeypatch):
    real_client = httpx.AsyncClient

    def fake_client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=transport())

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)


async def _run(tmp_path):
    captured = {}
    runner = APITestRunner(api_base_url="https://api.example", api_token="tok")
    result = await runner.run_test(
        CASE.query,
        case_to_expected(CASE),
        artifact_sink=lambda a: captured.update(a),
    )
    return result, captured


@pytest.mark.anyio
async def test_run_test_scores_and_captures(patched_client, tmp_path):
    result, artifact = await _run(tmp_path)
    assert result.trace_url == "https://lf/t-1"
    assert result.aoi_id_match_score == 1.0
    assert result.dataset_id_match_score == 1.0
    assert result.error is None
    assert result.overall_score == 1.0
    # extras flow through: uid arrived on the TestResult
    assert result.model_dump()["uid"] == CASE.uid
    # artifact carries the raw signals the CSVs used to drop
    assert artifact["statistics_last"]["data_rows_total"] == 1
    assert artifact["dataset"]["dataset_id"] == "11"


@pytest.mark.anyio
async def test_result_maps_to_ledger_entry(patched_client, tmp_path):
    result, _ = await _run(tmp_path)
    entry = result_to_entry(result, CASE.uid)
    assert entry["uid"] == CASE.uid
    assert entry["id"] == "1-002"
    assert entry["checks"]["aoi_id_match"] == 1.0
    assert entry["checks"]["nudge_match"] is None
    assert "overall" not in entry["checks"]
    assert entry["latency_s"] is not None


def test_merge_trials_majority_and_detail():
    trials = [
        {"uid": "u", "id": "1-002", "checks": {"aoi_id_match": 1.0}, "latency_s": 1.0},
        {"uid": "u", "id": "1-002", "checks": {"aoi_id_match": 0.0}, "latency_s": 2.0},
        {"uid": "u", "id": "1-002", "checks": {"aoi_id_match": 1.0}, "latency_s": 3.0},
    ]
    merged = merge_trials(trials)
    assert merged["checks"]["aoi_id_match"] == 1.0
    assert [t["latency_s"] for t in merged["trials"]] == [1.0, 2.0, 3.0]
    assert merge_trials(trials[:1]) == trials[0]


def test_artifact_writer_round_trip(tmp_path):
    from goldset.runner.artifacts import ArtifactWriter

    writer = ArtifactWriter(tmp_path, "run-x")
    path = writer("abc123", 1, {"tool_calls": [], "charts_data": None})
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        assert json.load(handle)["tool_calls"] == []
    assert path.name == "abc123.json.gz"
    assert writer("abc123", 2, {}).name == "abc123_t2.json.gz"


def test_failed_checks_carry_their_actuals():
    """Expected-vs-measured in reports needs the measured side recorded —
    on failures only, trimmed, absent when nothing failed."""
    from goldset.eval_types import TestResult

    result = TestResult(
        thread_id="t", query="q", overall_score=0.0, execution_time="now",
        test_id="1-002", aoi_id_match_score=0.0, actual_id="XYZ.9_1",
        agent_answer_score=0.0, actual_agent_answer="A" * 900,
        dataset_id_match_score=1.0, actual_dataset_id="4",
    )
    entry = result_to_entry(result, "u")
    assert entry["actuals"]["aoi_id_match"] == "XYZ.9_1"
    assert len(entry["actuals"]["agent_answer"]) == 300  # trimmed
    assert "dataset_id_match" not in entry["actuals"]  # passed: not recorded
