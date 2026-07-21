"""Phase 1 schema tests (cases 1-13 in tests/test_schemas.md)."""

import pytest
from pydantic import ValidationError

from app.schemas.intent import (
    AggregationSpec,
    AnalysisTask,
    DataRequirement,
    ExtractionSpec,
    QueryIntent,
)
from app.schemas.request import QueryRequest
from app.schemas.response import (
    ErrorResponse,
    InputInterpretation,
    PipelineResponse,
    ResponseMeta,
    VisualizationSpec,
)
from app.schemas.trial_record import (
    APICallRecord,
    FieldStatRecord,
    PipelineContext,
    StudyRecord,
)


# --- builders -------------------------------------------------------------


def make_viz(**overrides) -> VisualizationSpec:
    base = dict(
        task_id="t1",
        description="d",
        type="bar",
        type_category="categorical",
        title="T",
        encoding={"category": "phase_label", "value": "count"},
        data=[{"phase_label": "Phase 1", "count": 3}],
    )
    base.update(overrides)
    return VisualizationSpec(**base)


def make_study(**overrides) -> StudyRecord:
    base = dict(
        nct_id="NCT01",
        title="A study",
        status="RECRUITING",
        phases=["PHASE1"],
        phase_label="Phase 1",
        conditions=["Melanoma"],
        interventions=["DrugX"],
        intervention_types=["DRUG"],
        sponsor_name="Org",
        sponsor_class="INDUSTRY",
        start_year=2018,
        start_month=3,
        completion_year=2021,
        countries=["United States"],
        cities=["Boston"],
        enrollment=120,
        study_type="INTERVENTIONAL",
        excerpt="Phase 1 study of DrugX",
        source_query="DrugX",
    )
    base.update(overrides)
    return StudyRecord(**base)


def make_agg(**overrides) -> AggregationSpec:
    base = dict(group_by=["phase_label"], metric="count")
    base.update(overrides)
    return AggregationSpec(**base)


# --- 1-4: QueryRequest ----------------------------------------------------


def test_1_query_too_short_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(query="ab")


def test_2_invalid_input_mode_rejected():
    with pytest.raises(ValidationError):
        QueryRequest(query="how many trials", input_mode="bogus")


def test_3_full_input_accepted():
    r = QueryRequest(
        query="trials for X",
        input_mode="override",
        drug_name="X",
        condition="Y",
        sponsor="Z",
        trial_phase="PHASE1",
        trial_status="RECRUITING",
        country="US",
        start_year=2015,
        end_year=2020,
        include_citations=True,
        max_citations_per_group=10,
        max_studies=1000,
        viz_category_preference="temporal",
    )
    assert r.drug_name == "X"
    assert r.input_mode == "override"


def test_4_minimal_input_defaults():
    r = QueryRequest(query="abc")
    assert r.input_mode == "supplement"
    assert r.drug_name is None
    assert r.condition is None
    assert r.include_citations is False
    assert r.max_studies == 5000
    assert r.max_citations_per_group == 5


# --- 5-6: AggregationSpec output_mode ------------------------------------


def test_5_aggregation_valid_output_modes():
    for mode in ("aggregated", "raw_records", "edge_list"):
        assert make_agg(output_mode=mode).output_mode == mode


def test_6_aggregation_invalid_output_mode():
    with pytest.raises(ValidationError):
        make_agg(output_mode="pivot")


# --- 7-9: VisualizationSpec / AnalysisType Literals -----------------------


def test_7_viz_type_is_open_string():
    for t in ("heatmap", "custom_chart", "sankey_diagram"):
        assert make_viz(type=t).type == t


def test_8_viz_type_category_rejects_invalid():
    with pytest.raises(ValidationError):
        make_viz(type_category="bogus")


def test_9_candidate_viz_categories_rejects_invalid():
    with pytest.raises(ValidationError):
        AnalysisTask(
            task_id="t1",
            description="d",
            aggregation=make_agg(),
            candidate_viz_categories=["categorical", "not_a_category"],
        )


# --- 10: round-trip every model ------------------------------------------


def _one_of_each_model():
    study = make_study()
    agg = make_agg(sort_by="count", output_mode="aggregated")
    extraction = ExtractionSpec(needed=True, extract_as="dose")
    req = DataRequirement(
        requirement_id="r1",
        retrieval_strategy="study_search",
        search_params={"query.intr": "DrugX"},
        filter_params={"filter.phase": "PHASE1"},
        entity_tag="A",
    )
    task = AnalysisTask(
        task_id="t1",
        description="distribution by phase",
        aggregation=agg,
        extraction=extraction,
        candidate_viz_categories=["categorical", "distribution"],
    )
    intent = QueryIntent(
        original_query="q",
        query_complexity="simple",
        data_requirements=[req],
        tasks=[task],
        task_data_map={"t1": ["r1"]},
    )
    api_call = APICallRecord(
        endpoint="/studies",
        params={"pageSize": 1000},
        timestamp="2026-07-21T00:00:00Z",
        record_count=1,
        http_status=200,
        duration_ms=42,
    )
    ctx = PipelineContext(request_id="req-1")
    ctx.add_studies([study])
    interp = InputInterpretation(input_mode="supplement", from_query={"drug": "DrugX"})
    viz = make_viz()
    meta = ResponseMeta(
        request_id="req-1",
        original_query="q",
        input_mode="supplement",
        input_interpretation=interp,
        query_complexity="simple",
        filters_applied={"drug_name": "DrugX"},
        total_studies_analyzed=1,
        data_retrieval_strategy="study_search",
        api_calls=[api_call],
        stage_timings={"stage_1": 0.5},
        api_version="2.0.5",
        data_refresh="2026-07-21T09:00:05",
    )
    return [
        QueryRequest(query="abc"),
        agg,
        extraction,
        req,
        task,
        intent,
        study,
        FieldStatRecord(field_name="phase", field_value="PHASE1", count=10),
        api_call,
        ctx,
        interp,
        viz,
        meta,
        PipelineResponse(visualizations=[viz], meta=meta),
        ErrorResponse(error="bad", message="something", suggestion="try X"),
    ]


def test_10_all_models_round_trip():
    for model in _one_of_each_model():
        restored = type(model).model_validate(model.model_dump())
        assert restored == model, type(model).__name__


# --- 11-13: misc ----------------------------------------------------------


def test_11_study_record_all_none_optionals_valid():
    s = StudyRecord(
        nct_id="NCT02",
        title="t",
        status="UNKNOWN",
        phases=[],
        phase_label="N/A",
        conditions=[],
        interventions=[],
        intervention_types=[],
        sponsor_name=None,
        sponsor_class=None,
        start_year=None,
        start_month=None,
        completion_year=None,
        countries=[],
        cities=[],
        enrollment=None,
        study_type=None,
        excerpt="",
        source_query="q",
    )
    assert s.entity_tag is None
    assert s.enrollment is None


def test_12_pipeline_context_request_id_required():
    with pytest.raises(ValidationError):
        PipelineContext()  # missing request_id
    ctx = PipelineContext(request_id="req-1")
    assert ctx.request_id == "req-1"
    assert ctx.studies == {}


def test_13_error_response_required_fields():
    with pytest.raises(ValidationError):
        ErrorResponse(error="X")  # missing message
    e = ErrorResponse(error="bad", message="something")
    assert e.suggestion is None
    assert e.details == {}


# --- extra: PipelineContext helper behavior (anti-overfit: generic tagging) --


def test_context_entity_tags_and_helpers():
    ctx = PipelineContext(request_id="req-2")
    a = make_study(nct_id="NCT_A")
    b = make_study(nct_id="NCT_B")
    ctx.add_studies([a], entity_tag="DrugA")
    ctx.add_studies([b], entity_tag="DrugB")
    assert {s.nct_id for s in ctx.get_studies_by_tags(["DrugA"])} == {"NCT_A"}
    assert len(ctx.get_all_studies()) == 2
    ctx.add_note("n")
    ctx.add_warning("w")
    assert ctx.notes == ["n"] and ctx.warnings == ["w"]
