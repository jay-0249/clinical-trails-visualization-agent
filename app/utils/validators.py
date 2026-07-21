"""Validation gates that keep the LLM honest (Layer 1 of 2).

- validate_structured_hints runs BEFORE Stage 1: rejects bad enum values in the
  request so we fail fast (and cheap) without an LLM call.
- validate_intent runs AFTER Stage 1, BEFORE Stage 2: rejects a QueryIntent that
  references non-existent fields, invalid enum values, or an output_mode whose
  real requirements aren't met.

Requirements are driven by `_OUTPUT_MODE_REQUIREMENTS`, which mirrors what the
aggregator ACTUALLY needs per mode (see app/pipeline/aggregator.py, Layer 2) —
so we never reject a plan the aggregator would happily run (e.g. an edge_list
network that carries an unused metric). All valid values come from the
reference cache, never hardcoded.
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

# What each output_mode actually requires. Mirrors the aggregator's behavior:
# - aggregated: sum/unique_count do field math (crash without a field); >=1 group_by.
# - raw_records: metric_field is the value axis (crash without it); group_by optional.
# - edge_list: uses only the 2 group_by fields; metric/metric_field are ignored.
_OUTPUT_MODE_REQUIREMENTS = {
    "aggregated": {"needs_metric_field_for": ["sum", "unique_count"], "min_group_by": 1},
    "raw_records": {"needs_metric_field_always": True, "min_group_by": 0},
    "edge_list": {"needs_metric_field_for": [], "exact_group_by": 2},
}

# Which candidate category each non-default output_mode must be paired with.
_MODE_REQUIRES_CATEGORY = {"raw_records": "distribution", "edge_list": "relational"}


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
        mode = agg.output_mode
        reqs = _OUTPUT_MODE_REQUIREMENTS.get(mode, {})

        # group_by cardinality
        if "exact_group_by" in reqs and len(agg.group_by) != reqs["exact_group_by"]:
            raise IntentValidationError(
                f"output_mode '{mode}' requires exactly {reqs['exact_group_by']} "
                f"group_by fields, got {len(agg.group_by)}."
            )
        if len(agg.group_by) < reqs.get("min_group_by", 0):
            raise IntentValidationError(
                f"output_mode '{mode}' requires at least {reqs['min_group_by']} "
                f"group_by field(s), got {len(agg.group_by)}."
            )

        # group_by fields must exist on StudyRecord
        for field in agg.group_by:
            if field not in groupable:
                raise IntentValidationError(
                    f"group_by field '{field}' is not a groupable StudyRecord field. "
                    f"Valid fields: {sorted(groupable)}"
                )

        # metric_field requirements (only where the aggregator actually reads it)
        if reqs.get("needs_metric_field_always") and not agg.metric_field:
            raise IntentValidationError(
                f"output_mode '{mode}' requires a metric_field (the value field). "
                f"Valid fields: {sorted(groupable)}"
            )
        if agg.metric in reqs.get("needs_metric_field_for", []) and not agg.metric_field:
            raise IntentValidationError(
                f"metric '{agg.metric}' requires a metric_field in '{mode}' mode. "
                f"Valid fields: {sorted(groupable)}"
            )
        if agg.metric_field and agg.metric_field not in groupable:
            raise IntentValidationError(
                f"metric_field '{agg.metric_field}' is not a StudyRecord field. "
                f"Valid fields: {sorted(groupable)}"
            )

        # candidate categories valid (normally Literal-enforced; defensive)
        for cat in task.candidate_viz_categories:
            if cat not in VALID_CATEGORIES:
                raise IntentValidationError(
                    f"Invalid viz category '{cat}'. Valid: {sorted(VALID_CATEGORIES)}"
                )

        # output_mode <-> category consistency
        required_cat = _MODE_REQUIRES_CATEGORY.get(mode)
        if required_cat and required_cat not in set(task.candidate_viz_categories):
            raise IntentValidationError(
                f"output_mode '{mode}' requires '{required_cat}' in "
                "candidate_viz_categories."
            )
