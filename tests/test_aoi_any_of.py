"""``aoi_ids`` alternatives: ``|`` separates sets the selection may equal.

Some places have more than one defensible area (Salonga is a national park,
a World Heritage site and a KBA), and an all-of set can only name one.
"""

import pytest

from goldset.eval_types import ExpectedData
from goldset.evaluators.aoi_evaluator import evaluate_aoi_selection
from goldset.evaluators.dashboard_evaluator import evaluate_dashboard_aoi


def _state(*aois: tuple[str, str]) -> dict:
    return {"aoi_selection": {"aois": [{"src_id": src_id, "source": source, "name": src_id}
                                       for src_id, source in aois]}}


@pytest.mark.parametrize(("raw", "parsed"), [
    ("BRA", [["BRA"]]),
    ("PER;BOL;ECU", [["PER", "BOL", "ECU"]]),
    ("555697863|10906|6060", [["555697863"], ["10906"], ["6060"]]),
    ("PER.26.3 | PER8623;PER8624", [["PER.26.3"], ["PER8623", "PER8624"]]),
    ("A||B|", [["A"], ["B"]]),
    # '/' lists one area's equivalent records (draft-5 review, ch-comp-147)
    ("555697863/10906;2017/478291",
     [["555697863", "2017"], ["555697863", "478291"], ["10906", "2017"], ["10906", "478291"]]),
    ("A/B | C", [["A"], ["B"], ["C"]]),
    ("", []),
    (["BRA", "IDN"], [["BRA", "IDN"]]),
    ([["A"], ["B"]], [["A"], ["B"]]),
])
def test_aoi_ids_parse_into_alternatives(raw, parsed):
    assert ExpectedData(expected_aoi_ids=raw).expected_aoi_ids == parsed


def test_any_alternative_passes():
    expected = ExpectedData(expected_aoi_ids="555697863|10906").expected_aoi_ids
    assert evaluate_aoi_selection(_state(("10906", "wdpa")), expected)["aoi_id_match_score"] == 1.0
    assert evaluate_aoi_selection(_state(("555697863", "wdpa")), expected)["aoi_id_match_score"] == 1.0


def test_each_area_may_use_any_of_its_records():
    expected = ExpectedData(expected_aoi_ids="555697863/10906;2017/478291").expected_aoi_ids
    both = _state(("10906", "wdpa"), ("478291", "wdpa"))
    assert evaluate_aoi_selection(both, expected)["aoi_id_match_score"] == 1.0
    one_area = _state(("10906", "wdpa"))
    assert evaluate_aoi_selection(one_area, expected)["aoi_id_match_score"] == 0.0


def test_no_alternative_fails():
    expected = ExpectedData(expected_aoi_ids="555697863|10906").expected_aoi_ids
    assert evaluate_aoi_selection(_state(("6060", "kba")), expected)["aoi_id_match_score"] == 0.0


def test_each_alternative_is_still_an_exact_set():
    expected = ExpectedData(expected_aoi_ids="PER.26.3|PER8623;PER8624").expected_aoi_ids
    both = _state(("PER8623", "landmark"), ("PER8624", "landmark"))
    one = _state(("PER8624", "landmark"))
    mixed = _state(("PER.26.3_1", "gadm"), ("PER8624", "landmark"))
    assert evaluate_aoi_selection(both, expected)["aoi_id_match_score"] == 1.0
    assert evaluate_aoi_selection(one, expected)["aoi_id_match_score"] == 0.0
    assert evaluate_aoi_selection(mixed, expected)["aoi_id_match_score"] == 0.0


def test_gadm_suffix_normalised_within_an_alternative():
    expected = ExpectedData(expected_aoi_ids="15913|IDN.34.6").expected_aoi_ids
    assert evaluate_aoi_selection(_state(("IDN.34.6_1", "gadm")), expected)["aoi_id_match_score"] == 1.0


def test_no_selection_still_fails_with_alternatives():
    expected = ExpectedData(expected_aoi_ids="555697863|10906").expected_aoi_ids
    assert evaluate_aoi_selection({}, expected)["aoi_id_match_score"] == 0.0


def test_dashboard_aoi_matches_any_alternative():
    expected = ExpectedData(expected_aoi_ids="555697863|10906").expected_aoi_ids
    dashboard = {"aois": [{"src_id": "10906", "source": "wdpa"}]}
    assert evaluate_dashboard_aoi(dashboard, expected)["dashboard_aoi_match_score"] == 1.0
    other = {"aois": [{"src_id": "6060", "source": "kba"}]}
    assert evaluate_dashboard_aoi(other, expected)["dashboard_aoi_match_score"] == 0.0
