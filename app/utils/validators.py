"""Validation gates that keep the LLM honest.

- validate_structured_hints runs BEFORE Stage 1: rejects bad enum values in the
  request so we fail fast (and cheap) without an LLM call.
- validate_intent runs AFTER Stage 1, BEFORE Stage 2: rejects a QueryIntent that
  references non-existent fields, invalid enum values, or inconsistent
  output modes — catching hallucinations before they reach the API or pandas.

All valid values are read from the reference cache, never hardcoded.
"""

from fastapi import HTTPException

from app.schemas.intent import QueryIntent
from app.schemas.request import QueryRequest

VALID_CATEGORIES = {
    "categorical",
    "temporal",
    "relational",
    "spatial",
    "matrix",
    "hierarchical",
    "distribution",
}

# CT.gov enum filter params -> the reference-cache attribute holding valid values.
_FILTER_ENUM_ATTR = {
    "filter.phase": "valid_phases",
    "filter.overallStatus": "valid_statuses",
}

MAX_TASKS = 4
MAX_DATA_REQUIREMENTS = 5
_METRICS_NEEDING_FIELD = {"sum", "collect", "unique_count"}


class IntentValidationError(ValueError):
    """The LLM-produced QueryIntent failed a semantic validation check."""


def validate_structured_hints(request: QueryRequest, cache) -> None:
    """Reject invalid trial_phase / trial_status before the LLM runs (HTTP 400)."""
    if request.trial_phase and request.trial_phase not in cache.valid_phases:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_phase",
                "message": f"trial_phase '{request.trial_phase}' is not a valid phase.",
                "valid_values": cache.valid_phases,
            },
        )
    if request.trial_status and request.trial_status not in cache.valid_statuses:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "invalid_status",
                "message": f"trial_status '{request.trial_status}' is not a valid status.",
                "valid_values": cache.valid_statuses,
            },
        )


def validate_intent(intent: QueryIntent, cache) -> None:
    """Validate an LLM-produced QueryIntent; raise IntentValidationError on failure."""
    if len(intent.tasks) > MAX_TASKS:
        raise IntentValidationError(
            f"Too many analysis tasks: {len(intent.tasks)} (max {MAX_TASKS})."
        )
    if len(intent.data_requirements) > MAX_DATA_REQUIREMENTS:
        raise IntentValidationError(
            f"Too many data requirements: {len(intent.data_requirements)} "
            f"(max {MAX_DATA_REQUIREMENTS})."
        )

    # Filter-param enum values must be valid CT.gov enum tokens.
    for req in intent.data_requirements:
        for key, attr in _FILTER_ENUM_ATTR.items():
            raw = (req.filter_params or {}).get(key)
            if not raw:
                continue
            valid = getattr(cache, attr)
            for token in str(raw).split("|"):
                token = token.strip()
                if token and token not in valid:
                    raise IntentValidationError(
                        f"Invalid value '{token}' for {key}. Valid values: {valid}"
                    )

    groupable = set(cache.groupable_fields)
    for task in intent.tasks:
        agg = task.aggregation

        for field in agg.group_by:
            if field not in groupable:
                raise IntentValidationError(
                    f"group_by field '{field}' is not a groupable StudyRecord field. "
                    f"Valid fields: {sorted(groupable)}"
                )

        if agg.metric in _METRICS_NEEDING_FIELD:
            if not agg.metric_field or agg.metric_field not in groupable:
                raise IntentValidationError(
                    f"metric '{agg.metric}' requires a valid metric_field "
                    f"(a StudyRecord field); got {agg.metric_field!r}. "
                    f"Valid fields: {sorted(groupable)}"
                )

        for cat in task.candidate_viz_categories:
            if cat not in VALID_CATEGORIES:
                raise IntentValidationError(
                    f"Invalid viz category '{cat}'. Valid: {sorted(VALID_CATEGORIES)}"
                )

        cats = set(task.candidate_viz_categories)
        if agg.output_mode == "raw_records" and "distribution" not in cats:
            raise IntentValidationError(
                "output_mode 'raw_records' requires 'distribution' in "
                "candidate_viz_categories."
            )
        if agg.output_mode == "edge_list":
            if "relational" not in cats:
                raise IntentValidationError(
                    "output_mode 'edge_list' requires 'relational' in "
                    "candidate_viz_categories."
                )
            if len(agg.group_by) != 2:
                raise IntentValidationError(
                    "output_mode 'edge_list' requires exactly 2 group_by fields, "
                    f"got {len(agg.group_by)}."
                )
