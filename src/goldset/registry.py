"""Evaluator registry: named, typed dispatch for the ported evaluators.

The runner iterates ``EVALUATORS`` in order and merges each result dict —
the order below reproduces gnw-evals' hand-written ``_run_evaluations``
call sequence exactly (later evaluators win key collisions, as before).

PR-05 extends the spec with bucket tags; PR-03 keeps it behaviour-neutral.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from goldset.eval_types import ExpectedData
from goldset.evaluators import (
    evaluate_aoi_selection,
    evaluate_clarification,
    evaluate_dashboard_aoi,
    evaluate_dashboard_created,
    evaluate_dashboard_widgets,
    evaluate_data_pull,
    evaluate_dataset_selection,
    evaluate_date_extraction,
    evaluate_date_selection,
    evaluate_final_answer,
    evaluate_nudge,
    evaluate_suggested_datasets,
)

EvaluatorFn = Callable[
    [dict[str, Any], ExpectedData, str, dict[str, Any] | None],
    dict[str, Any],
]


@dataclass(frozen=True)
class EvaluatorSpec:
    name: str
    kind: str  # "deterministic" | "llm_judge" | "mixed"
    score_fields: tuple[str, ...]
    run: EvaluatorFn


EVALUATORS: tuple[EvaluatorSpec, ...] = (
    EvaluatorSpec(
        name="clarification",
        kind="llm_judge",
        score_fields=("clarification_requested_score",),
        run=lambda state, expected, query, dashboard: evaluate_clarification(
            state, expected.expected_clarification, query
        ),
    ),
    EvaluatorSpec(
        name="aoi",
        kind="deterministic",
        score_fields=("aoi_id_match_score",),
        run=lambda state, expected, query, dashboard: evaluate_aoi_selection(
            state, expected.expected_aoi_ids, query
        ),
    ),
    EvaluatorSpec(
        name="dataset",
        kind="deterministic",
        score_fields=(
            "dataset_id_match_score",
            "dataset_parameter_match_score",
            "context_layer_match_score",
        ),
        run=lambda state, expected, query, dashboard: evaluate_dataset_selection(
            state,
            expected.expected_dataset_id,
            expected.expected_dataset_parameters,
            expected.expected_context_layer,
            query,
        ),
    ),
    EvaluatorSpec(
        name="date_coverage",
        kind="deterministic",
        score_fields=("date_coverage_score",),
        run=lambda state, expected, query, dashboard: evaluate_date_selection(
            state,
            expected_start_date=expected.expected_start_date,
            expected_end_date=expected.expected_end_date,
        ),
    ),
    EvaluatorSpec(
        name="date_extraction",
        kind="deterministic",
        score_fields=("date_extraction_score",),
        run=lambda state, expected, query, dashboard: evaluate_date_extraction(
            state,
            expected_start_date=expected.expected_start_date,
            expected_end_date=expected.expected_end_date,
        ),
    ),
    EvaluatorSpec(
        name="data_pull",
        kind="deterministic",
        score_fields=("data_pull_exists_score",),
        run=lambda state, expected, query, dashboard: evaluate_data_pull(
            state, expects_data_pull=expected.expects_data_pull(), query=query
        ),
    ),
    EvaluatorSpec(
        name="answer",
        kind="mixed",
        score_fields=(
            "charts_answer_score",
            "agent_answer_score",
            "expected_text_match_score",
        ),
        run=lambda state, expected, query, dashboard: evaluate_final_answer(
            state, expected.expected_answer, expected.expected_text, query
        ),
    ),
    EvaluatorSpec(
        name="suggested_datasets",
        kind="deterministic",
        score_fields=("suggested_datasets_match_score",),
        run=lambda state, expected, query, dashboard: evaluate_suggested_datasets(
            state, expected.expected_suggested_datasets
        ),
    ),
    EvaluatorSpec(
        name="nudge",
        kind="deterministic",
        score_fields=("nudge_match_score",),
        run=lambda state, expected, query, dashboard: evaluate_nudge(
            state, expected.expected_nudge_type, expected.expected_nudge_options
        ),
    ),
    EvaluatorSpec(
        name="dashboard_created",
        kind="deterministic",
        score_fields=("dashboard_created_score",),
        run=lambda state, expected, query, dashboard: evaluate_dashboard_created(
            state, expected.expected_dashboard_created
        ),
    ),
    EvaluatorSpec(
        name="dashboard_aoi",
        kind="deterministic",
        score_fields=("dashboard_aoi_match_score",),
        run=lambda state, expected, query, dashboard: evaluate_dashboard_aoi(
            dashboard, expected.expected_aoi_ids, expected.expected_aoi_source
        ),
    ),
    EvaluatorSpec(
        name="dashboard_widgets",
        kind="deterministic",
        score_fields=(
            "dashboard_widgets_match_score",
            "dashboard_widgets_valid_score",
        ),
        run=lambda state, expected, query, dashboard: evaluate_dashboard_widgets(
            dashboard, expected.expected_dashboard_widgets
        ),
    ),
)

EVALUATOR_NAMES: frozenset[str] = frozenset(spec.name for spec in EVALUATORS)

ALL_SCORE_FIELDS: tuple[str, ...] = tuple(
    field for spec in EVALUATORS for field in spec.score_fields
)
