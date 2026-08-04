"""End-to-end runner test against a mocked API — no network, no judge.

Covers: streamed chat POST, trace capture, state fetch, evaluation via the
registry, artifact capture, and the CLI's result->ledger-entry mapping.
"""

import gzip
import json
import time

import anyio
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


def test_run_record_names_its_caseset():
    """A run must say which store it loaded, not just the content hash —
    caseset_version alone can't tell a reader v1 from v2 without git
    archaeology over the manifests."""
    import argparse

    from goldset.cli import build_run_record
    from goldset.ledger import validate_run

    args = argparse.Namespace(
        run_id="20260804T120000Z_staging_experimental", build="b", ff="experimental",
        trials=3, workers=10, trial_timeout=900.0, note=None,
        cases_dir=__import__("pathlib").Path("cases/v2"),
    )
    entries = [{"uid": "u1", "id": "1-001", "checks": {"aoi_id_match": 1.0}}]
    record = build_run_record(
        args, {"caseset_version": "2276185a231bfdad"}, entries,
        started="2026-08-04T12:00:00Z", environment="staging",
    )
    assert record["caseset"] == "v2"
    assert record["caseset_version"] == "2276185a231bfdad"
    assert validate_run(record) == []


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


class _KeepaliveStream(httpx.AsyncByteStream):
    """A stream that never finishes but keeps every per-read timeout happy —
    the exact staging failure mode of 2026-08-01."""

    async def __aiter__(self):
        yield b'{"node": "keepalive"}\n'
        while True:
            await anyio.sleep(0.02)
            yield b"\n"


class _HangingTransport(httpx.AsyncBaseTransport):
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=_KeepaliveStream(), request=request)


@pytest.mark.anyio
async def test_wall_clock_limit_bounds_a_keepalive_stream(monkeypatch):
    """The per-read HTTP timeout resets on every keepalive; only the
    wall-clock limit can end such a trial — as an error row, quickly."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=_HangingTransport()),
    )
    runner = APITestRunner(
        api_base_url="https://api.example",
        api_token="tok",
        wall_clock_limit=0.3,
    )
    start = time.monotonic()
    result = await runner.run_test(CASE.query, case_to_expected(CASE))
    assert time.monotonic() - start < 5.0
    assert "wall-clock" in (result.error or "")
    assert result.aoi_id_match_score is None
