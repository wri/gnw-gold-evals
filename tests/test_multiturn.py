"""Multiturn semantics (PR-07): identity, deltas, store, and a full
two-turn conversation against a stateful mocked API."""

import json

import httpx
import pytest

from goldset.canonical import conversation_uid
from goldset.cli import result_to_entry
from goldset.runner.api import APITestRunner
from goldset.runner.multiturn import (
    evaluate_deltas,
    flatten_turn_checks,
    run_conversation,
)
from goldset.store import Case, read_case, write_case

TURNS = (
    {"query": "How much tree cover loss did Brazil have in 2022?",
     "expected": {"aoi_ids": "BRA", "dataset_id": "4"}},
    {"query": "And for Indonesia?",
     "expected": {"aoi_ids": "IDN"},
     "deltas": {"changed": ["aoi_ids"], "retain": ["dataset_id"]}},
)

CASE = Case(id="mt-x", status="ready", group="multiturn", turns=TURNS)


# --- identity

def test_conversation_uid_is_order_sensitive():
    reordered = (TURNS[1], TURNS[0])
    assert conversation_uid(TURNS) != conversation_uid(reordered)


def test_conversation_uid_ignores_deltas_and_metadata():
    without_deltas = (
        TURNS[0],
        {"query": TURNS[1]["query"], "expected": TURNS[1]["expected"]},
    )
    assert conversation_uid(TURNS) == conversation_uid(without_deltas)
    changed = (TURNS[0], {**TURNS[1], "expected": {"aoi_ids": "MYS"}})
    assert conversation_uid(TURNS) != conversation_uid(changed)


# --- store

def test_multiturn_round_trip(tmp_path):
    path = write_case(tmp_path, CASE)
    loaded, stored_uid = read_case(path)
    assert loaded == CASE
    assert stored_uid == CASE.uid
    assert loaded.is_multiturn


def test_multiturn_validation():
    with_query = Case(id="x", status="ready", group="g", query="q", turns=TURNS)
    assert any("must not set query" in p for p in with_query.validate())
    one_turn = Case(id="x", status="ready", group="g", turns=(TURNS[0],))
    assert any("at least 2 turns" in p for p in one_turn.validate())
    turn1_deltas = Case(id="x", status="ready", group="g",
                        turns=({**TURNS[0], "deltas": {"changed": ["aoi_ids"]}},
                               TURNS[1]))
    assert any("turn 1 cannot assert deltas" in p for p in turn1_deltas.validate())


# --- deltas

def test_delta_assertions():
    prev = {"aoi_ids": "BRA", "dataset_id": "4", "context_layer": "primary_forest"}
    cur = {"aoi_ids": "IDN", "dataset_id": "4", "context_layer": ""}
    ok = evaluate_deltas(prev, cur, {"changed": ["aoi_ids"],
                                     "retain": ["dataset_id"],
                                     "absent": ["context_layer"]})
    assert ok["state_delta_score"] == 1.0

    stale = evaluate_deltas(prev, {**cur, "aoi_ids": "BRA"}, {"changed": ["aoi_ids"]})
    assert stale["state_delta_score"] == 0.0
    assert "should have changed" in stale["state_delta_reason"]

    lost = evaluate_deltas(prev, {**cur, "dataset_id": "0"}, {"retain": ["dataset_id"]})
    assert lost["state_delta_score"] == 0.0

    leak = evaluate_deltas(prev, {**cur, "context_layer": "primary_forest"},
                           {"absent": ["context_layer"]})
    assert "contamination" in leak["state_delta_reason"]

    unknown = evaluate_deltas(prev, cur, {"changed": ["not_a_field"]})
    assert unknown["state_delta_score"] is None


def test_flatten_turn_checks():
    flat = flatten_turn_checks([
        {"checks": {"aoi_id_match": 1.0}},
        {"checks": {"aoi_id_match": 0.0, "state_delta": 1.0}},
    ])
    assert flat == {"t1.aoi_id_match": 1.0,
                    "t2.aoi_id_match": 0.0, "t2.state_delta": 1.0}


def test_turn_prefixed_checks_resolve_buckets_and_verdicts():
    from goldset.buckets import buckets_for, row_verdict

    assert buckets_for("t2.aoi_id_match") == ("retrieval",)
    assert buckets_for("t1.state_delta") == ("retrieval",)
    assert row_verdict({"checks": {"t1.aoi_id_match": 1.0,
                                   "t2.state_delta": 0.0}}) == "fail"
    assert row_verdict({"checks": {"t1.date_coverage": 0.0}}) == "uncovered"


# --- the conversation loop, end to end against a stateful mock

def _state(aoi, dataset):
    return {
        "aoi_selection": {"aois": [{"src_id": aoi, "name": aoi,
                                    "subtype": "country", "source": "gadm"}]},
        "dataset": {"dataset_id": dataset, "dataset_name": "TCL",
                    "parameters": [], "context_layer": None},
        "messages": [], "charts_data": [], "codeact_parts": [],
        "statistics": [{"source_url": "https://api/x", "id": "p1",
                        "data": [{"year": 2022, "area_ha": 1.0}]}],
    }


@pytest.fixture
def stateful_transport(monkeypatch):
    seen = {"chats": 0, "thread_ids": set()}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/chat":
            seen["chats"] += 1
            seen["thread_ids"].add(json.loads(request.content)["thread_id"])
            return httpx.Response(200, text=json.dumps(
                {"node": "trace_info",
                 "update": json.dumps({"trace_id": "t", "trace_url": "https://lf/t"})}
            ))
        if request.url.path.startswith("/api/threads/"):
            state = _state("BRA", "4") if seen["chats"] == 1 else _state("IDN", "4")
            return httpx.Response(200, json={"state": json.dumps(state)})
        raise AssertionError(request.url)

    real_client = httpx.AsyncClient

    def fake_client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    return seen


@pytest.mark.anyio
async def test_two_turn_conversation(stateful_transport):
    runner = APITestRunner(api_base_url="https://api.example", api_token="tok")
    entry = await run_conversation(runner, CASE, result_to_entry)

    # one thread, two POSTs — the continuation mechanism
    assert stateful_transport["chats"] == 2
    assert len(stateful_transport["thread_ids"]) == 1

    checks = entry["checks"]
    assert checks["t1.aoi_id_match"] == 1.0  # BRA as expected
    assert checks["t2.aoi_id_match"] == 1.0  # IDN as expected
    assert checks["t2.state_delta"] == 1.0   # aoi changed, dataset retained
    assert entry["uid"] == CASE.uid
    assert len(entry["turns_detail"]) == 2
