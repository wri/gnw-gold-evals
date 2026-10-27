"""An attempt that got no reply is a failed attempt, not an error (AJ,
2026-10-27). ch-comp-053 in 20261027T103249Z_prod: attempt 2's stream went
silent for 240 s (ReadTimeout), and the row was dropped as an error although
attempts 1 and 3 had both answered wrongly."""

import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import benchmark_page as bp  # noqa: E402
import challenge_rollup as cr  # noqa: E402
from compose_runs import _all_trials_clean  # noqa: E402

from goldset.buckets import row_verdict  # noqa: E402
from goldset.cli import merge_trials, result_to_entry  # noqa: E402
from goldset.eval_types import ExpectedData  # noqa: E402
from goldset.runner.api import APITestRunner, got_no_answer  # noqa: E402

PASS = {"aoi_id_match": 1.0, "dataset_id_match": 1.0}
FAIL = {"aoi_id_match": 1.0, "dataset_id_match": 0.0}
SILENT = {"aoi_id_match": None, "dataset_id_match": None}


def _trial(checks, **extra):
    return {"uid": "u", "id": "ch-x", "checks": dict(checks), **extra}


# ------------------------------------------------------------ the runner


def _status_error(status):
    request = httpx.Request("POST", "https://api.example/api/chat")
    return httpx.HTTPStatusError("x", request=request,
                                 response=httpx.Response(status, request=request))


@pytest.mark.parametrize(("error", "stream_s", "expected"), [
    (httpx.ReadTimeout("silent"), None, True),
    (TimeoutError(), None, True),            # the wall clock
    (httpx.RemoteProtocolError("dropped"), None, True),
    (_status_error(503), None, True),
    (_status_error(401), None, False),       # our token, not Horizon
    (httpx.ConnectError("no route"), None, False),
    (ValueError("bad line"), None, False),
    (httpx.ReadTimeout("state GET"), 12.0, False),  # the reply had finished
])
def test_which_errors_left_the_user_without_a_reply(error, stream_s, expected):
    assert got_no_answer(error, stream_s) is expected


@pytest.mark.anyio
async def test_a_stalled_stream_is_recorded_as_no_answer(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("no bytes for 240 s", request=request)

    real_client = httpx.AsyncClient

    def fake_client(**kwargs):
        kwargs.pop("timeout", None)
        return real_client(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "AsyncClient", fake_client)
    runner = APITestRunner(api_base_url="https://api.example", api_token="tok")
    result = await runner.run_test("q", ExpectedData(test_id="ch-x"))
    assert result.no_answer is True
    entry = result_to_entry(result, "u")
    assert entry["no_answer"] == "no bytes for 240 s"
    assert "error" not in entry


def test_a_harness_error_stays_an_error():
    # Not at module level: pytest would try to collect it.
    from goldset.eval_types import TestResult

    result = TestResult(thread_id="t", query="q", overall_score=0.0,
                        execution_time="now", error="state GET failed")
    entry = result_to_entry(result, "u")
    assert entry["error"] == "state GET failed" and "no_answer" not in entry


# ------------------------------------------------------------- the merge


def test_ch_comp_053_is_a_fail_not_an_error():
    merged = merge_trials([
        _trial(FAIL), _trial(SILENT, no_answer="ReadTimeout"), _trial(FAIL),
    ])
    assert "error" not in merged and "no_answer" not in merged
    assert merged["trials"][1]["no_answer"] == "ReadTimeout"
    assert row_verdict(merged) == "fail"
    assert not cr.strict_clean(merged)


@pytest.mark.parametrize(("attempts", "verdict"), [
    ([PASS, "no reply", PASS], "pass"),   # right on 2 of 3
    ([PASS, "no reply", FAIL], "fail"),
    (["no reply", "no reply", PASS], "fail"),
    (["no reply"] * 3, "fail"),
])
def test_no_reply_counts_as_a_failed_attempt(attempts, verdict):
    merged = merge_trials([
        _trial(SILENT, no_answer="ReadTimeout") if a == "no reply" else _trial(a)
        for a in attempts
    ])
    assert row_verdict(merged) == verdict


def test_an_unscored_attempt_is_left_out():
    merged = merge_trials([
        _trial(FAIL, error="state GET failed"), _trial(PASS), _trial(PASS),
    ])
    assert merged["checks"] == PASS     # the unscored FAIL takes no part
    assert merged["trials"][0]["error"] == "state GET failed"
    assert row_verdict(merged) == "pass"
    assert cr.strict_clean(merged)
    assert _all_trials_clean(merged)


def test_a_single_attempt_with_no_reply_fails():
    assert row_verdict(_trial(SILENT, no_answer="ReadTimeout")) == "fail"


# -------------------------------------------------------------- the page


def test_the_page_counts_no_reply_attempts_and_names_them():
    no_reply = merge_trials([
        _trial(PASS), _trial(SILENT, no_answer="ReadTimeout"), _trial(PASS),
    ])
    unscored = merge_trials([
        _trial(PASS), _trial(FAIL, error="state GET failed"), _trial(PASS),
    ])
    stats = bp.group_stats([no_reply, unscored])
    assert (stats["scored"], stats["errors"], stats["passed"]) == (2, 0, 2)
    assert (stats["attempts"], stats["no_answer"]) == (6, 1)
    # Right every time: the no-reply attempt was wrong; the unscored one
    # does not count against the other question.
    assert stats["every_time"] == 0.5
    assert [bp.attempt_error(t) for t in no_reply["trials"]] == [
        None, {"kind": "no_answer", "reason": "ReadTimeout"}, None]
    assert bp.attempt_error(unscored["trials"][1]) == {
        "kind": "unscored", "reason": "state GET failed"}
    json.dumps(stats)  # page data stays plain JSON
