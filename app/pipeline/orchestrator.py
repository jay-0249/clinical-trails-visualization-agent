"""The per-request pipeline: NL query -> PipelineResponse.

execute() chains the four stages, applies the input_mode merge, tracks a
request_id + per-stage timings, and assembles the response metadata. Errors
raise typed exceptions; build_error_response maps any of them to a structured
ErrorResponse (used here and by the FastAPI endpoint in Phase 10).
"""

import logging
import uuid

from fastapi import HTTPException

from app.pipeline.aggregator import AggregationError, aggregate
from app.pipeline.data_retriever import fetch_data
from app.pipeline.query_analyzer import QueryAnalysisError, analyze
from app.pipeline.viz_generator import VizGenerationError, generate
from app.schemas.intent import QueryIntent
from app.schemas.request import QueryRequest
from app.schemas.response import (
    ErrorResponse,
    InputInterpretation,
    PipelineResponse,
    ResponseMeta,
)
from app.schemas.trial_record import PipelineContext
from app.utils.logger import get_logger, log_event, timed_stage
from app.utils.validators import (
    IntentValidationError,
    validate_intent,
    validate_structured_hints,
)

_logger = get_logger("orchestrator")

# Structured request hint -> CT.gov param. Only query.intr is entity-specific
# (used per comparison arm); the rest are common filters/searches.
_SEARCH_HINTS = {
    "drug_name": "query.intr",
    "condition": "query.cond",
    "sponsor": "query.spons",
    "country": "query.locn",
}
_FILTER_HINTS = {
    "trial_phase": "filter.phase",
    "trial_status": "filter.overallStatus",
}
_HINT_FIELDS = [
    "drug_name",
    "condition",
    "sponsor",
    "trial_phase",
    "trial_status",
    "country",
    "start_year",
    "end_year",
]


def _provided_hints(request: QueryRequest) -> dict:
    return {f: getattr(request, f) for f in _HINT_FIELDS if getattr(request, f) is not None}


def _hints_to_params(request: QueryRequest) -> tuple[dict, dict]:
    search = {p: getattr(request, f) for f, p in _SEARCH_HINTS.items() if getattr(request, f)}
    filters = {p: getattr(request, f) for f, p in _FILTER_HINTS.items() if getattr(request, f)}
    return search, filters


def merge_and_validate(
    intent: QueryIntent, request: QueryRequest, ctx: PipelineContext
) -> tuple[QueryIntent, InputInterpretation]:
    """Combine the query-derived intent with structured hints per input_mode."""
    mode = request.input_mode
    provided = _provided_hints(request)
    hint_search, hint_filters = _hints_to_params(request)
    interp = InputInterpretation(input_mode=mode)

    if mode == "query_only":
        interp.ignored_params = provided
        interp.resolution = "Structured params ignored; intent taken from query only."
        return intent, interp

    if mode == "override":
        interp.from_params = provided
        collapsed = len(intent.data_requirements) > 1
        first = intent.data_requirements[0]
        first.search_params = dict(hint_search)
        first.filter_params = dict(hint_filters)
        first.entity_tag = None
        intent.data_requirements = [first]
        for task in intent.tasks:  # entity_tag grouping is meaningless with one arm
            stripped = [f for f in task.aggregation.group_by if f != "entity_tag"]
            task.aggregation.group_by = stripped or task.aggregation.group_by
        intent.task_data_map = {t.task_id: [first.requirement_id] for t in intent.tasks}
        if collapsed:
            intent.query_complexity = "simple"
            msg = "Comparison collapsed to a single entity (override params describe one entity)."
            interp.conflicts.append(msg)
            ctx.add_warning(msg)
        interp.resolution = "Structured params are the sole filter source (override)."
        return intent, interp

    # supplement (default): query is primary; params confirm/add and win conflicts.
    interp.from_params = provided
    interp.from_query = {
        r.requirement_id: {**r.search_params, **r.filter_params} for r in intent.data_requirements
    }
    conflicts: list[str] = []
    for req in intent.data_requirements:
        is_arm = req.entity_tag is not None and len(intent.data_requirements) > 1
        for key, value in hint_search.items():
            # An intervention hint applies only to the matching comparison arm.
            if is_arm and key == "query.intr" and req.entity_tag.lower() != str(value).lower():
                continue
            existing = req.search_params.get(key)
            if existing is not None and existing != value:
                conflicts.append(f"{key}: query '{existing}' vs param '{value}' — param applied")
            req.search_params[key] = value
        for key, value in hint_filters.items():
            existing = req.filter_params.get(key)
            if existing is not None and existing != value:
                conflicts.append(f"{key}: query '{existing}' vs param '{value}' — param applied")
            req.filter_params[key] = value
    for c in conflicts:
        ctx.add_conflict(c)
    interp.conflicts = conflicts
    interp.resolution = "Query is primary; structured params confirm/add (supplement)."
    return intent, interp


def _collect_filters(intent: QueryIntent) -> dict:
    out: dict = {}
    for req in intent.data_requirements:
        out.update(req.search_params)
        out.update(req.filter_params)
    return out


def build_meta(request, intent, ctx, interpretation, reference_cache) -> ResponseMeta:
    strategies = sorted({r.retrieval_strategy for r in intent.data_requirements})
    return ResponseMeta(
        request_id=ctx.request_id,
        original_query=intent.original_query,
        input_mode=request.input_mode,
        input_interpretation=interpretation,
        query_complexity=intent.query_complexity,
        filters_applied=_collect_filters(intent),
        total_studies_analyzed=len(ctx.get_all_studies()),
        data_retrieval_strategy=",".join(strategies),
        api_calls=ctx.api_calls_made,
        stage_timings=ctx.stage_timings,
        api_version=reference_cache.api_version,
        data_refresh=reference_cache.last_refresh,
        notes=ctx.notes,
        limitations=ctx.limitations,
        warnings=ctx.warnings,
    )


_ERROR_MAP = {
    "IntentValidationError": (
        "invalid_query_plan",
        "The query could not be turned into a valid analysis plan.",
        "Rephrase with a clearer analysis intent (e.g. 'distribution of X by phase').",
    ),
    "QueryAnalysisError": (
        "query_analysis_failed",
        "Failed to interpret the query.",
        "Rephrase the question, or check that OPENAI_API_KEY is set.",
    ),
    "AggregationError": (
        "aggregation_failed",
        "The analysis plan could not be executed on the retrieved data.",
        None,
    ),
    "VizGenerationError": (
        "viz_generation_failed",
        "Failed to produce a visualization specification.",
        None,
    ),
}


def build_error_response(exc: Exception, request_id: str | None = None) -> ErrorResponse:
    """Map any pipeline exception to a structured ErrorResponse."""
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return ErrorResponse(
            error=detail.get("error", "invalid_request"),
            message=detail.get("message", str(exc.detail)),
            details={**detail, "request_id": request_id},
        )
    code, message, suggestion = _ERROR_MAP.get(
        type(exc).__name__, ("internal_error", "An unexpected error occurred.", None)
    )
    return ErrorResponse(
        error=code,
        message=f"{message} ({exc})"[:400],
        suggestion=suggestion,
        details={"type": type(exc).__name__, "request_id": request_id},
    )


async def execute(request: QueryRequest, reference_cache, ct_client) -> PipelineResponse:
    """Run the full pipeline. Raises typed exceptions on failure."""
    request_id = str(uuid.uuid4())
    ct_client.request_id = request_id
    ctx = PipelineContext(
        request_id=request_id,
        api_version=reference_cache.api_version,
        last_data_refresh=reference_cache.last_refresh,
        enums=reference_cache.enums,
    )
    log_event(
        _logger,
        logging.INFO,
        "pipeline_start",
        request_id=request_id,
        query=request.query,
        input_mode=request.input_mode,
    )

    validate_structured_hints(request, reference_cache)  # HTTP 400 on bad enum

    with timed_stage(_logger, ctx, "query_analysis"):
        intent = await analyze(
            request.query,
            _provided_hints(request),
            request.input_mode,
            reference_cache,
            request_id=request_id,
        )
        validate_intent(intent, reference_cache)

    intent, interpretation = merge_and_validate(intent, request, ctx)

    with timed_stage(_logger, ctx, "data_retrieval"):
        for req in intent.data_requirements:
            await fetch_data(req, ct_client, ctx, request.max_studies)
    ctx.api_calls_made = list(ct_client.api_calls)

    visualizations = []
    for task in intent.tasks:
        req_ids = intent.task_data_map.get(task.task_id, [])
        tags = [
            r.entity_tag
            for r in intent.data_requirements
            if r.requirement_id in req_ids and r.entity_tag
        ]
        studies = ctx.get_studies_by_tags(tags) if tags else ctx.get_all_studies()

        with timed_stage(_logger, ctx, f"aggregation_{task.task_id}"):
            aggregated = aggregate(
                studies,
                task.aggregation,
                include_citations=request.include_citations,
                max_citations_per_group=request.max_citations_per_group,
            )
        if not aggregated:
            ctx.add_note(f"Task {task.task_id}: no data after aggregation.")

        with timed_stage(_logger, ctx, f"viz_generation_{task.task_id}"):
            viz = await generate(
                task, aggregated, intent.original_query, request_id=request_id
            )
        visualizations.append(viz)

    log_event(
        _logger,
        logging.INFO,
        "pipeline_complete",
        request_id=request_id,
        studies=len(ctx.get_all_studies()),
        visualizations=len(visualizations),
    )
    return PipelineResponse(
        visualizations=visualizations,
        meta=build_meta(request, intent, ctx, interpretation, reference_cache),
    )


# Silence unused-import checkers for exceptions re-exported for callers/tests.
__all__ = [
    "execute",
    "merge_and_validate",
    "build_meta",
    "build_error_response",
    "AggregationError",
    "QueryAnalysisError",
    "VizGenerationError",
    "IntentValidationError",
]
