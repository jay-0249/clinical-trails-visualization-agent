"""Stage 2 — execute a DataRequirement against the CT.gov client.

Maps the LLM's abstract retrieval strategy to concrete client calls and folds
the results (and any truncation) into the PipelineContext. The client already
merges search_params/filter_params, so this layer just routes by strategy.
"""

from app.schemas.intent import DataRequirement
from app.schemas.trial_record import PipelineContext
from app.services.ct_client import CTGovClient


async def fetch_data(
    requirement: DataRequirement,
    ct_client: CTGovClient,
    ctx: PipelineContext,
    max_records: int,
) -> None:
    """Fetch data for one requirement and add it to the context."""
    strategy = requirement.retrieval_strategy

    if strategy == "field_stats":
        field = (requirement.search_params or {}).get("field") or (
            requirement.search_params or {}
        ).get("field_name")
        if not field:
            ctx.add_limitation(
                f"Requirement {requirement.requirement_id}: field_stats with no "
                "field specified; skipped."
            )
            return
        stats = await ct_client.get_field_stats(field, requirement.filter_params or {})
        ctx.field_stats.extend(stats)
        return

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
    records, truncation = await ct_client.search_studies(requirement, max_records)
    ctx.add_studies(records, entity_tag=requirement.entity_tag)
    if truncation:
        ctx.add_limitation(
            f"Requirement {requirement.requirement_id}: analyzed "
            f"{truncation.returned} of {truncation.total_available} matching "
            f"studies ({truncation.reason})."
        )
