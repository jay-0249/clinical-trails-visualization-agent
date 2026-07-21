"""Input schema — the public request contract (documented in README)."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    query: str = Field(
        ..., min_length=3, description="Natural language question about clinical trials"
    )

    input_mode: Literal["supplement", "override", "query_only"] = Field(
        "supplement",
        description=(
            "How to combine query text and structured params. "
            "supplement: query is primary, params confirm/add. "
            "override: params are the filtering source of truth. "
            "query_only: ignore all structured params."
        ),
    )

    drug_name: str | None = Field(None, description="Intervention/drug name")
    condition: str | None = Field(None, description="Disease/condition")
    sponsor: str | None = Field(None, description="Sponsor organization")
    trial_phase: str | None = Field(
        None, description="Phase filter, validated against API enums"
    )
    trial_status: str | None = Field(
        None, description="Status filter, validated against API enums"
    )
    country: str | None = Field(None, description="Country for geographic filtering")
    start_year: int | None = Field(None, ge=1990, le=2030)
    end_year: int | None = Field(None, ge=1990, le=2030)

    include_citations: bool = False
    max_citations_per_group: int = Field(5, ge=1, le=50)
    max_studies: int = Field(5000, ge=1, le=10000)
    viz_category_preference: str | None = None
