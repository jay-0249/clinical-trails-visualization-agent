"""Phase 5 validator tests (cases 3.1-3.8), with a mock reference cache."""

import types

import pytest
from fastapi import HTTPException

from app.schemas.intent import AggregationSpec, AnalysisTask, DataRequirement, QueryIntent
from app.schemas.request import QueryRequest
from app.schemas.trial_record import StudyRecord
from app.utils.validators import (
    IntentValidationError,
    validate_intent,
    validate_structured_hints,
)


def mock_cache():
    return types.SimpleNamespace(
        valid_phases=["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"],
        valid_statuses=["RECRUITING", "COMPLETED", "TERMINATED", "ACTIVE_NOT_RECRUITING"],
        valid_sponsor_classes=["INDUSTRY", "NIH", "FED", "OTHER"],
        groupable_fields=list(StudyRecord.model_fields.keys()),
    )


# --- builders -------------------------------------------------------------


def agg(group_by=None, metric="count", output_mode="aggregated", metric_field=None):
    return AggregationSpec(
        group_by=group_by if group_by is not None else ["phase_label"],
        metric=metric,
        output_mode=output_mode,
        metric_field=metric_field,
    )


def task(task_id="t1", categories=None, aggregation=None):
    return AnalysisTask(
        task_id=task_id,
        description="d",
        aggregation=aggregation or agg(),
        candidate_viz_categories=categories or ["categorical"],
    )


def req(rid="r1", filter_params=None):
    return DataRequirement(
        requirement_id=rid,
        retrieval_strategy="study_search",
        search_params={},
        filter_params=filter_params or {},
    )


def intent(tasks=None, reqs=None):
    tsks = tasks or [task()]
    rqs = reqs or [req()]
    return QueryIntent(
        original_query="q",
        query_complexity="simple",
        data_requirements=rqs,
        tasks=tsks,
        task_data_map={t.task_id: [r.requirement_id for r in rqs] for t in tsks},
    )


# --- 3.1 valid ------------------------------------------------------------


def test_3_1_valid_intent_passes():
    validate_intent(intent(), mock_cache())  # no raise


def test_3_1b_valid_structured_hints_pass():
    validate_structured_hints(
        QueryRequest(query="abc", trial_phase="PHASE3", trial_status="RECRUITING"),
        mock_cache(),
    )  # no raise


# --- 3.2 invalid phase in filter_params -----------------------------------


def test_3_2_invalid_filter_phase():
    it = intent(reqs=[req(filter_params={"filter.phase": "Phase3"})])
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "PHASE3" in str(exc.value)  # valid values listed


# --- 3.3 invalid group_by field -------------------------------------------


def test_3_3_invalid_group_by_field():
    it = intent(tasks=[task(aggregation=agg(group_by=["nonexistent_field"]))])
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "nonexistent_field" in str(exc.value)
    assert "phase_label" in str(exc.value)  # valid fields listed


# --- 3.4 too many tasks ---------------------------------------------------


def test_3_4_too_many_tasks():
    it = intent(tasks=[task(task_id=f"t{i}") for i in range(5)])
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "max 4" in str(exc.value)


# --- 3.5 too many data requirements ---------------------------------------


def test_3_5_too_many_requirements():
    it = intent(reqs=[req(rid=f"r{i}") for i in range(6)])
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "max 5" in str(exc.value)


# --- 3.6 edge_list needs exactly 2 group_by -------------------------------


def test_3_6_edge_list_needs_two_fields():
    it = intent(
        tasks=[
            task(
                categories=["relational"],
                aggregation=agg(group_by=["sponsor_name"], output_mode="edge_list"),
            )
        ]
    )
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "exactly 2" in str(exc.value)


def test_3_6b_edge_list_two_fields_ok():
    it = intent(
        tasks=[
            task(
                categories=["relational"],
                aggregation=agg(
                    group_by=["sponsor_name", "interventions"], output_mode="edge_list"
                ),
            )
        ]
    )
    validate_intent(it, mock_cache())  # no raise


# --- 3.7 raw_records without distribution ---------------------------------


def test_3_7_raw_records_without_distribution():
    it = intent(
        tasks=[
            task(
                categories=["categorical"],
                aggregation=agg(output_mode="raw_records", metric_field="enrollment"),
            )
        ]
    )
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "distribution" in str(exc.value)


def test_3_7b_raw_records_with_distribution_ok():
    it = intent(
        tasks=[
            task(
                categories=["distribution"],
                aggregation=agg(output_mode="raw_records", metric_field="enrollment"),
            )
        ]
    )
    validate_intent(it, mock_cache())  # no raise


# --- two-layer regression: edge_list ignores metric/metric_field ----------


def test_q4_edge_list_collect_no_metric_field_passes():
    # The Q4 network plan the LLM produced: edge_list + metric=collect + no
    # metric_field. The aggregator ignores the metric here, so validation passes.
    it = intent(
        tasks=[
            task(
                categories=["relational"],
                aggregation=agg(
                    group_by=["sponsor_name", "interventions"],
                    metric="collect",
                    output_mode="edge_list",
                ),
            )
        ]
    )
    validate_intent(it, mock_cache())  # no raise


def test_aggregated_collect_without_metric_field_passes():
    # 'collect' is NOT in aggregated.needs_metric_field_for (it degrades to []).
    it = intent(tasks=[task(aggregation=agg(metric="collect", output_mode="aggregated"))])
    validate_intent(it, mock_cache())  # no raise


def test_raw_records_requires_metric_field():
    it = intent(
        tasks=[
            task(
                categories=["distribution"],
                aggregation=agg(group_by=[], output_mode="raw_records", metric_field=None),
            )
        ]
    )
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "metric_field" in str(exc.value)


# --- 3.8 invalid trial_phase in request (before LLM) ----------------------


def test_3_8_invalid_trial_phase_400():
    with pytest.raises(HTTPException) as exc:
        validate_structured_hints(
            QueryRequest(query="abc", trial_phase="PHASE99"), mock_cache()
        )
    assert exc.value.status_code == 400
    assert "PHASE3" in exc.value.detail["valid_values"]


def test_3_8b_invalid_trial_status_400():
    with pytest.raises(HTTPException) as exc:
        validate_structured_hints(
            QueryRequest(query="abc", trial_status="GOING_STRONG"), mock_cache()
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["error"] == "invalid_status"


# --- metric_field requirement ---------------------------------------------


def test_metric_field_required_for_sum():
    it = intent(tasks=[task(aggregation=agg(metric="sum", metric_field=None))])
    with pytest.raises(IntentValidationError) as exc:
        validate_intent(it, mock_cache())
    assert "metric_field" in str(exc.value)


def test_metric_field_valid_for_unique_count():
    it = intent(
        tasks=[task(aggregation=agg(metric="unique_count", metric_field="sponsor_name"))]
    )
    validate_intent(it, mock_cache())  # no raise
