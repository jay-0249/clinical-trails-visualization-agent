"""Phase 9 — orchestrator. Hermetic merge/error tests + live end-to-end."""

import types

import pytest
from fastapi import HTTPException

from app.config import Settings
from app.pipeline.orchestrator import (
    build_error_response,
    execute,
    merge_and_validate,
)
from app.schemas.intent import AggregationSpec, AnalysisTask, DataRequirement, QueryIntent
from app.schemas.request import QueryRequest
from app.schemas.response import PipelineResponse
from app.schemas.trial_record import StudyRecord
from app.services.ct_client import CTGovClient
from app.services.reference_cache import ReferenceDataCache
from app.utils.validators import IntentValidationError


# --- builders -------------------------------------------------------------


def _req(rid, search=None, filt=None, tag=None):
    return DataRequirement(
        requirement_id=rid,
        retrieval_strategy="study_search",
        search_params=search or {},
        filter_params=filt or {},
        entity_tag=tag,
    )


def _task(tid="t1", group_by=None, categories=None):
    return AnalysisTask(
        task_id=tid,
        description="d",
        aggregation=AggregationSpec(group_by=group_by or ["phase_label"], metric="count"),
        candidate_viz_categories=categories or ["categorical"],
    )


def _intent(reqs, tasks=None, complexity="simple"):
    tasks = tasks or [_task()]
    return QueryIntent(
        original_query="q",
        query_complexity=complexity,
        data_requirements=reqs,
        tasks=tasks,
        task_data_map={t.task_id: [r.requirement_id for r in reqs] for t in tasks},
    )


def _ctx():
    from app.schemas.trial_record import PipelineContext

    return PipelineContext(request_id="rid")


def mock_cache():
    return types.SimpleNamespace(
        valid_phases=["PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"],
        valid_statuses=["RECRUITING", "COMPLETED"],
        valid_sponsor_classes=["INDUSTRY", "NIH"],
        groupable_fields=list(StudyRecord.model_fields.keys()),
        api_version="2.0.5",
        last_refresh="2026-07-21T09:00:05",
        enums={},
    )


# --- merge_and_validate: query_only ---------------------------------------


def test_query_only_ignores_params():
    intent = _intent([_req("r1", search={"query.intr": "FromQuery"})])
    req = QueryRequest(query="trends", drug_name="Pembrolizumab", input_mode="query_only")
    merged, interp = merge_and_validate(intent, req, _ctx())
    assert merged.data_requirements[0].search_params == {"query.intr": "FromQuery"}
    assert interp.ignored_params == {"drug_name": "Pembrolizumab"}
    assert interp.input_mode == "query_only"


# --- merge_and_validate: override -----------------------------------------


def test_override_replaces_params():
    intent = _intent([_req("r1", search={"query.intr": "Wrong"})])
    req = QueryRequest(
        query="distribution",
        drug_name="Pembrolizumab",
        trial_phase="PHASE3",
        input_mode="override",
    )
    merged, interp = merge_and_validate(intent, req, _ctx())
    r = merged.data_requirements[0]
    assert r.search_params == {"query.intr": "Pembrolizumab"}
    assert r.filter_params == {"filter.phase": "PHASE3"}
    assert interp.from_params["drug_name"] == "Pembrolizumab"


def test_override_collapses_comparison():
    intent = _intent(
        [_req("r1", tag="Pembrolizumab"), _req("r2", tag="Nivolumab")],
        tasks=[_task(group_by=["phase_label", "entity_tag"])],
        complexity="comparative",
    )
    req = QueryRequest(query="compare", drug_name="Pembrolizumab", input_mode="override")
    ctx = _ctx()
    merged, interp = merge_and_validate(intent, req, ctx)
    assert len(merged.data_requirements) == 1
    assert merged.data_requirements[0].entity_tag is None
    assert merged.query_complexity == "simple"
    assert merged.tasks[0].aggregation.group_by == ["phase_label"]  # entity_tag stripped
    assert ctx.warnings  # collapse warned


# --- merge_and_validate: supplement ---------------------------------------


def test_supplement_applies_and_logs_conflict():
    intent = _intent([_req("r1", search={"query.intr": "QueryDrug"})])
    req = QueryRequest(query="show trials", drug_name="ParamDrug", input_mode="supplement")
    ctx = _ctx()
    merged, interp = merge_and_validate(intent, req, ctx)
    assert merged.data_requirements[0].search_params["query.intr"] == "ParamDrug"  # param wins
    assert interp.conflicts and any("param applied" in c for c in interp.conflicts)
    assert ctx.conflicts


def test_supplement_comparison_arm_targeting():
    intent = _intent(
        [
            _req("r1", search={"query.intr": "Pembrolizumab"}, tag="Pembrolizumab"),
            _req("r2", search={"query.intr": "Nivolumab"}, tag="Nivolumab"),
        ],
        complexity="comparative",
    )
    # A drug hint should confirm only the matching arm, not overwrite the other.
    req = QueryRequest(query="compare", drug_name="Pembrolizumab", input_mode="supplement")
    merged, _ = merge_and_validate(intent, req, _ctx())
    arms = {r.entity_tag: r.search_params["query.intr"] for r in merged.data_requirements}
    assert arms == {"Pembrolizumab": "Pembrolizumab", "Nivolumab": "Nivolumab"}


# --- build_error_response -------------------------------------------------


def test_build_error_response_intent_error():
    err = build_error_response(IntentValidationError("bad plan"), request_id="rid")
    assert err.error == "invalid_query_plan"
    assert err.details["request_id"] == "rid"
    assert err.suggestion


def test_build_error_response_http_exception():
    exc = HTTPException(
        status_code=400,
        detail={"error": "invalid_phase", "message": "bad", "valid_values": ["PHASE3"]},
    )
    err = build_error_response(exc, request_id="rid")
    assert err.error == "invalid_phase"
    assert err.details["valid_values"] == ["PHASE3"]


# --- execute error path (hermetic — fails at pre-validation, no network) ---


async def test_execute_rejects_invalid_phase():
    req = QueryRequest(query="phase distribution", trial_phase="PHASE99")
    client = CTGovClient(Settings(_env_file=None))
    with pytest.raises(HTTPException) as exc:
        await execute(req, mock_cache(), client)
    assert exc.value.status_code == 400


# --- full end-to-end (live) ------------------------------------------------


@pytest.mark.integration
async def test_e2e_simple_query():
    cache = ReferenceDataCache(Settings(_env_file=None))
    await cache.load()
    client = CTGovClient(Settings(_env_file=None))
    client.page_size = 50  # keep the e2e light
    req = QueryRequest(
        query="How are Pembrolizumab trials distributed across phases?", max_studies=50
    )
    resp = await execute(req, cache, client)

    assert isinstance(resp, PipelineResponse)
    assert resp.visualizations
    v = resp.visualizations[0]
    assert v.type_category == "categorical"
    assert v.data  # non-empty, injected from aggregation
    # metadata fully populated
    m = resp.meta
    assert m.request_id
    assert m.stage_timings and "query_analysis" in m.stage_timings
    assert m.total_studies_analyzed > 0
    assert m.api_calls
    assert m.input_interpretation.input_mode == "supplement"
    assert m.api_version and m.data_refresh
    print(
        f"\n[e2e] {v.type}/{v.type_category} | studies={m.total_studies_analyzed} "
        f"| stages={list(m.stage_timings)} | limitations={m.limitations}"
    )
