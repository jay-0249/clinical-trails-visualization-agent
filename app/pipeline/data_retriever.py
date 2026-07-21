"""Stage 2 — execute a DataRequirement against the CT.gov client.

Maps the LLM's abstract retrieval strategy to concrete client calls and folds
the results (and any truncation) into the PipelineContext. Search/filter params
are whitelisted before they reach the API, so a hallucinated param (e.g. a
`start_year` the LLM invented) is stripped and noted rather than causing a 400.
"""

import logging

from app.schemas.intent import DataRequirement
from app.schemas.trial_record import PipelineContext
from app.services.ct_client import CTGovClient
from app.utils.logger import get_logger, log_event

_logger = get_logger("data_retriever")

# The closed set of CT.gov API params we support. Anything else is stripped.
_ALLOWED_PARAMS = {
    # free-text search
    "query.cond",
    "query.intr",
    "query.term",
    "query.spons",
    "query.locn",
    # enum filters
    "filter.phase",
    "filter.overallStatus",
    "filter.geo",
    # pagination / control (added by the client, whitelisted for completeness)
    "pageSize",
    "pageToken",
    "countTotal",
    "sort",
    "format",
    "fields",
}


def _strip_unsupported_params(requirement: DataRequirement, ctx: PipelineContext) -> None:
    """Drop any search/filter param not in the CT.gov whitelist (mutates req)."""
    stripped: list[str] = []
    for attr in ("search_params", "filter_params"):
        params = getattr(requirement, attr) or {}
        clean = {k: v for k, v in params.items() if k in _ALLOWED_PARAMS}
        stripped.extend(k for k in params if k not in _ALLOWED_PARAMS)
        setattr(requirement, attr, clean)
    if stripped:
        ctx.add_note(f"Stripped unsupported API params: {', '.join(stripped)}")
        log_event(
            _logger,
            logging.WARNING,
            "params_stripped",
            request_id=ctx.request_id,
            requirement=requirement.requirement_id,
            stripped=stripped,
        )


async def fetch_data(
    requirement: DataRequirement,
    ct_client: CTGovClient,
    ctx: PipelineContext,
    max_records: int,
) -> None:
    """Fetch data for one requirement and add it to the context."""
    strategy = requirement.retrieval_strategy

    if strategy == "field_stats":
        # field_stats (pre-aggregated counts) is a v2 feature and isn't wired into
        # the StudyRecord-based aggregator. Fall back to record-level study_search
        # (capped) so the query still returns a real, if sampled, result.
        log_event(
            _logger,
            logging.WARNING,
            "field_stats_fallback",
            request_id=ctx.request_id,
            requirement=requirement.requirement_id,
            message="field_stats strategy is v2; falling back to study_search with cap",
        )
        ctx.add_note("Used study_search (capped sample) instead of field_stats (v2).")
        # fall through to the study_search path below

    if strategy == "study_detail":
        nct_id = (requirement.search_params or {}).get("nct_id")
        if not nct_id:
            ctx.add_limitation(
                f"Requirement {requirement.requirement_id}: study_detail with no "
                "nct_id; skipped."
            )
            return
        record = await ct_client.get_study_detail(nct_id)
        ctx.add_studies([record], entity_tag=requirement.entity_tag)
        return

    # study_search (and "combined") — the default record-level retrieval.
    _strip_unsupported_params(requirement, ctx)
    records, truncation = await ct_client.search_studies(requirement, max_records)
    ctx.add_studies(records, entity_tag=requirement.entity_tag)
    if truncation:
        ctx.add_limitation(
            f"Requirement {requirement.requirement_id}: analyzed "
            f"{truncation.returned} of {truncation.total_available} matching "
            f"studies ({truncation.reason})."
        )
