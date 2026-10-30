"""The plain baseline's scoring, outcomes and Sonnet transport — no network."""

import json
from types import SimpleNamespace

import pytest

from goldset.evaluators import figures
from goldset.plain import judges, outcome, overlay, score, sonnet
from goldset.plain.overlay import Calls
from goldset.store import Case

DEFAULT = Calls()


def _attempt(label="answered", offer=None, **checks):
    return {"label": label, "offer": offer, "checks": checks}


# ------------------------------------------------------------------ outcomes


@pytest.mark.parametrize("attempt, calls, expected", [
    ({"no_answer": True}, DEFAULT, "wrong"),
    ({"error": "judge down"}, DEFAULT, None),
    (_attempt(expected_text_match=1.0, figure_match=1.0), DEFAULT, "right"),
    (_attempt(expected_text_match=1.0, figure_match=0.0), DEFAULT, "wrong"),
    (_attempt(), DEFAULT, "uncovered"),
    # A decline passes a lenient "explains the limit" text, yet is no answer.
    (_attempt("declined", expected_text_match=1.0), DEFAULT, "declined"),
    (_attempt("declined", expected_text_match=1.0), Calls(decline_right=True), "right"),
    (_attempt("declined", expected_text_match=0.0), Calls(decline_right=True), "declined"),
    (_attempt("asked_back", offer=1.0), DEFAULT, "right"),
    (_attempt("asked_back", offer=0.0), DEFAULT, "declined"),
    # A Horizon-only text stops gating: the figure decides.
    (_attempt(expected_text_match=0.0, figure_match=1.0), Calls(text="horizon_only"), "right"),
    (_attempt(expected_text_match=1.0, figure_match=0.0), Calls(figure_info_only=True), "right"),
])
def test_attempt_outcomes(attempt, calls, expected):
    assert outcome.attempt_outcome(attempt, calls) == expected


def test_a_question_is_right_on_most_scored_attempts():
    right = _attempt(figure_match=1.0)
    wrong = _attempt(figure_match=0.0)
    assert outcome.question([right, right, wrong], DEFAULT).outcome == "right"
    # An uncovered attempt is left out: 1 of 1 scored.
    assert outcome.question([right, _attempt(), _attempt()], DEFAULT).outcome == "right"
    # Ties fail, as in BENCHMARK.
    assert outcome.question([right, wrong], DEFAULT).outcome == "wrong"


def test_declined_or_wrong_whichever_is_commoner_a_tie_wrong():
    declined = _attempt("declined")
    wrong = _attempt(figure_match=0.0)
    right = _attempt(figure_match=1.0)
    assert outcome.question([declined, declined, wrong], DEFAULT).outcome == "declined"
    assert outcome.question([declined, wrong, right], DEFAULT).outcome == "wrong"
    assert outcome.question([_attempt(), _attempt()], DEFAULT).outcome == "uncovered"


def test_benchmark_style_ignores_the_label():
    declined = _attempt("declined", expected_text_match=1.0)
    result = outcome.question([declined] * 3, DEFAULT)
    assert (result.outcome, result.benchmark) == ("declined", "pass")


def test_wrong_figure_needs_an_answer_with_a_failed_figure():
    wrong = _attempt(figure_match=0.0)
    assert outcome.question([wrong, wrong, _attempt(figure_match=1.0)], DEFAULT).wrong_figure
    assert not outcome.question([_attempt("declined", figure_match=0.0)] * 3,
                                DEFAULT).wrong_figure
    assert not outcome.question([wrong] * 3, Calls(figure_info_only=True)).wrong_figure


def test_summary_counts_uncovered_in_the_denominator():
    results = {
        "a": outcome.QuestionResult("right", "pass", False, ()),
        "b": outcome.QuestionResult("uncovered", "uncovered", False, ()),
    }
    summary = outcome.summarise(results)
    assert summary["rates"]["right"] == 0.5
    assert summary["uncovered"] == 1


def test_paired_gap_is_seeded_and_brackets_the_gap():
    first = {str(i): i % 2 == 0 for i in range(100)}
    second = {str(i): i % 4 == 0 for i in range(100)}
    gap = outcome.paired_gap(first, second, first)
    assert gap == outcome.paired_gap(first, second, first)
    assert gap["gap"] == 0.25
    assert gap["low"] < 0.25 < gap["high"]


# ------------------------------------------------------------------ overlay


def _overlay(tmp_path, questions, **header):
    path = tmp_path / "overlay.json"
    path.write_text(json.dumps({"schema_version": 1, **header, "questions": questions}))
    return path


def test_overlay_reads_calls(tmp_path):
    path = _overlay(tmp_path, {"u1": {"id": "ch-1", "text": "horizon_only",
                                      "areas": {"643": "kba"}, "why": "concession limit"}},
                    status="draft")
    header, calls = overlay.load(path, {"u1"})
    assert header["status"] == "draft"
    assert calls["u1"] == Calls(text="horizon_only", areas=(("643", "kba"),))


@pytest.mark.parametrize("entry, members, message", [
    ({"id": "x", "txt": "any"}, {"u1"}, "unknown overlay keys"),
    ({"id": "x", "text": "sometimes"}, {"u1"}, "text must be"),
    ({"id": "x", "areas": {"1": "moon"}}, {"u1"}, "unknown area sources"),
    ({"id": "x"}, {"u2"}, "not draft-5 members"),
])
def test_overlay_fails_loudly(tmp_path, entry, members, message):
    with pytest.raises(ValueError, match=message):
        overlay.load(_overlay(tmp_path, {"u1": entry}), members)


# -------------------------------------------------------------------- score


CASE = Case(id="ch-q", status="ready", group="g", query="How much loss in Brazil in 2020?",
            expected={"aoi_ids": "BRA", "dataset_id": "4",
                      "figure": "sum(area_ha) where tree_cover_loss_year = 2020",
                      "accept_nudge_offering": "4;8 | 9"})


def test_a_nudge_reads_as_its_buttons():
    text = score.as_read("Which dataset?", {"options": ["Tree cover loss", "Drivers"]})
    assert text.endswith("[Options offered as buttons: Tree cover loss; Drivers]")
    assert score.as_read("Plain.", None) == "Plain."


def test_offer_options_are_names_per_fair_offer():
    names = {"4": "Tree cover loss", "8": "Tree cover loss by dominant driver"}
    assert score.offer_options(CASE, names, {}) == [
        ["Tree cover loss", "Tree cover loss by dominant driver"], ["9"],
    ]


def test_horizons_nudge_path_is_read_on_its_own_pulls():
    nudge = {"type": "dataset_choice", "data": [{"dataset_id": 4}, {"dataset_id": 8}]}
    assert score.horizon_nudge_offer(CASE, nudge, []) == 1.0
    # It pulled data as well: the pull path, so the reply checks speak.
    assert score.horizon_nudge_offer(CASE, nudge, ["http://a/x/1"]) is None


@pytest.fixture
def table(monkeypatch):
    """The reference table the figure check fetches by link."""
    figures._fetch.cache_clear()
    monkeypatch.setattr(figures, "_fetch", lambda url: (
        ("tree_cover_loss_year", "area_ha"), ((2019, 100.0), (2020, 1500.0)),
    ))


def test_figures_are_checked_against_the_reference(monkeypatch, table):
    monkeypatch.setattr(judges, "label", lambda q, r: {"label": "answered", "reason": "r"})
    right = score.score_attempt(CASE, "About 1,500 ha were lost in 2020.", ["http://a/x/1"])
    wrong = score.score_attempt(CASE, "About 2,000 ha were lost in 2020.", ["http://a/x/1"])
    assert right["checks"]["figure_match"] == 1.0
    assert wrong["checks"]["figure_match"] == 0.0
    # Without a reference the figure check abstains rather than fails.
    none = score.score_attempt(CASE, "About 1,500 ha.", [])
    assert none["checks"]["figure_match"] is None


def test_an_ask_back_is_read_against_each_fair_offer(monkeypatch, table):
    monkeypatch.setattr(judges, "label", lambda q, r: {"label": "asked_back", "reason": "r"})
    seen = []

    def offers(query, reply, options):
        seen.append(options)
        return {"offers_all": options == ["9"], "reason": "r"}

    monkeypatch.setattr(judges, "offers", offers)
    attempt = score.score_attempt(CASE, "Do you mean sLUC?", [], offers=[["a", "b"], ["9"]])
    assert attempt["offer"] == 1.0 and len(seen) == 2


def test_no_text_is_no_reply_and_a_nudge_skips_the_judges(monkeypatch):
    monkeypatch.setattr(judges, "label", lambda q, r: pytest.fail("judged"))
    assert score.score_attempt(CASE, "  ", []) == {"no_answer": True}
    assert score.score_attempt(CASE, "Which?", [], nudge_offer=0.0)["offer"] == 0.0


def test_a_judge_outage_is_an_error_not_a_verdict(monkeypatch):
    def down(q, r):
        raise RuntimeError("overloaded")

    monkeypatch.setattr(judges, "label", down)
    assert "overloaded" in score.score_attempt(CASE, "1,500 ha", [])["error"]


# ------------------------------------------------------------------- sonnet


def _response(stop, text="", searches=0, input_tokens=0):
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=100,
                            cache_read_input_tokens=0, cache_creation_input_tokens=0,
                            server_tool_use=SimpleNamespace(web_search_requests=searches,
                                                            web_fetch_requests=0))
    content = [SimpleNamespace(type="text", text=text)] if text else []
    return SimpleNamespace(stop_reason=stop, content=content, usage=usage, model="m")


class _Api:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)


def test_sonnet_resumes_a_paused_turn_and_sums_usage():
    api = _Api([_response("pause_turn", searches=3), _response("end_turn", "1,500 ha")])
    answer = sonnet.ask("q", "2026-11-03", api=api)
    assert answer["reply"] == "1,500 ha" and not answer["stopped"]
    assert answer["usage"]["searches"] == 3 and answer["usage"]["requests"] == 2
    assert api.calls[0]["system"] == "You are Claude, a helpful assistant. Today's date is 2026-11-03."
    assert {t["max_uses"] for t in api.calls[0]["tools"]} == {10}


def test_sonnet_stops_at_a_dollar_with_no_reply():
    # 500k input tokens at $2/MTok is $1: the pause after it is the stop.
    api = _Api([_response("pause_turn", input_tokens=500_000), _response("end_turn", "late")])
    answer = sonnet.ask("q", "2026-11-03", api=api)
    assert answer["stopped"] and answer["reply"] == ""
    assert len(api.calls) == 1


def test_spend_cap_refuses_new_questions():
    spend = sonnet.Spend(1.0)
    spend.add(1.0)
    with pytest.raises(sonnet.CostCap):
        spend.check()
