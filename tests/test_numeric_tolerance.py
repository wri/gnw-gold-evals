"""Unit tests for the answer judge's numeric tolerance.

The judge only extracts which number in the prose answers the question
(`extracted_number`); `resolve_answer_verdict` applies the tolerance in code, the
same way `resolve_chart_verdict` already does for charts. What's testable without
an API call: that the tolerance constant is single-sourced and reaches the prompt,
that the prompt does not ask the model to compute a match itself, that splicing the
fragment in has not broken the LangChain placeholders (a stray `{` in a shared
fragment becomes a template variable and the judge call fails at runtime), and that
the deterministic override behaves correctly on its own.

Usage
$ uv run python -m pytest tests/test_numeric_tolerance.py -v
"""

from langchain_core.prompts import ChatPromptTemplate

from goldset.evaluators.llm_judges import (
    _NUMERIC_RULES,
    ANSWER_JUDGE_PROMPT,
    NUMERIC_TOLERANCE,
    resolve_answer_verdict,
)

TOLERANCE_PCT = f"{NUMERIC_TOLERANCE:.0%}"


def test_tolerance_is_two_percent():
    """The agreed threshold. Changing it should be a deliberate, visible edit."""
    assert NUMERIC_TOLERANCE == 0.02


def test_answer_judge_prompt_states_the_tolerance_and_the_extraction_field():
    """The deterministic override decides numeric rows on this figure, so the
    prompt must carry it and must tell the model what to extract."""
    assert f"{TOLERANCE_PCT} tolerance" in ANSWER_JUDGE_PROMPT
    assert "extracted_number" in ANSWER_JUDGE_PROMPT
    assert _NUMERIC_RULES in ANSWER_JUDGE_PROMPT


def test_prompt_does_not_ask_the_model_to_compute_the_match():
    """Regression guard: the model must not be asked to do the arithmetic itself
    again — that's the defect this change fixes (1-009: the judge accepted a
    0.51% delta in one trial and rejected the same delta in another)."""
    assert "Tolerance formula" not in _NUMERIC_RULES
    assert "MATCH (1)" not in _NUMERIC_RULES
    assert "NO MATCH (0)" not in _NUMERIC_RULES


def test_numeric_rules_add_no_template_variables():
    """A stray brace in the fragment would become a required input variable."""
    assert (
        ChatPromptTemplate.from_messages([("user", _NUMERIC_RULES)]).input_variables
        == []
    )


def test_assembled_prompt_exposes_exactly_the_expected_variables():
    """Guards against the fragment capturing or dropping a placeholder."""
    answer = ChatPromptTemplate.from_messages([("user", ANSWER_JUDGE_PROMPT)])
    assert sorted(answer.input_variables) == ["actual_answer", "expected_answer"]


# --------------------------------------------------------- resolve_answer_verdict

def test_deterministic_check_overrides_a_wrong_judge_rejection():
    """1-009's actual defect: the judge rejected a delta that is inside tolerance."""
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="3.93%",
        extracted_number="3.95%",
        judge_score=0,
        judge_reason="0.51% exceeds the 2% tolerance",
    )
    assert verdict["score"] == 1
    assert "deterministic check" in verdict["reason"]


def test_deterministic_check_overrides_a_wrong_judge_acceptance():
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="100 hectares",
        extracted_number="110 hectares",
        judge_score=1,
        judge_reason="close enough",
    )
    assert verdict["score"] == 0


def test_boundary_is_inclusive():
    """100 vs 102 is exactly 2%; the boundary is inclusive."""
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="100 hectares",
        extracted_number="102 hectares",
        judge_score=0,
        judge_reason="looked off",
    )
    assert verdict["score"] == 1


def test_unit_conversion_is_handled_in_code_not_by_the_model():
    """Expected in kha, extracted in hectares — same value, different units."""
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="200 kha",
        extracted_number="200,000 hectares",
        judge_score=0,
        judge_reason="units did not look the same",
    )
    assert verdict["score"] == 1


def test_non_numeric_rows_are_untouched():
    """Boolean/year/named_entity rows never had the arithmetic bug; leave them to
    the judge exactly as before."""
    verdict = resolve_answer_verdict(
        answer_eval_type="named_entity",
        expected_answer="Brazil",
        extracted_number="",
        judge_score=1,
        judge_reason="clearly Brazil",
    )
    assert verdict == {"score": 1, "reason": "clearly Brazil"}


def test_falls_back_to_the_judge_when_extraction_is_empty():
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="198.4 hectares",
        extracted_number="",
        judge_score=1,
        judge_reason="best guess",
    )
    assert verdict == {"score": 1, "reason": "best guess"}


def test_falls_back_to_the_judge_when_extraction_does_not_parse():
    """An ambiguous decimal ("230.003") can't be resolved deterministically —
    same abstention rule the chart comparator uses."""
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="230.003 hectares",
        extracted_number="230.003 hectares",
        judge_score=1,
        judge_reason="looked identical",
    )
    assert verdict == {"score": 1, "reason": "looked identical"}


def test_falls_back_to_the_judge_on_a_percent_unit_mismatch():
    """Expected is a percentage, extracted number is not — a parsing artifact,
    not the population this override is meant to fix."""
    verdict = resolve_answer_verdict(
        answer_eval_type="numeric",
        expected_answer="0.20%",
        extracted_number="5 hectares",
        judge_score=0,
        judge_reason="wrong quantity entirely",
    )
    assert verdict == {"score": 0, "reason": "wrong quantity entirely"}
