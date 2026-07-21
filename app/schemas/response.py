"""Output schema — the frontend-facing contract (documented in README).

VisualizationSpec.type is an open string (any chart name); type_category is
a Literal that constrains the encoding structure to one of 7 renderers.
"""

from pydantic import BaseModel

from app.schemas.intent import VizCategory
from app.schemas.trial_record import APICallRecord


class InputInterpretation(BaseModel):
    """Shows the caller what came from the query vs the structured params."""

    input_mode: str
    from_query: dict = {}
    from_params: dict = {}
    conflicts: list[str] = []
    resolution: str = ""
    ignored_params: dict = {}


class VisualizationSpec(BaseModel):
    task_id: str
    description: str
    type: str  # OPEN string — any chart type (e.g. "bar", "sankey", "choropleth")
    type_category: VizCategory  # constrains the encoding contract
    title: str
    encoding: dict
    data: list[dict]
    rendering_hints: dict = {}
    citations: list[dict] | None = None


class ResponseMeta(BaseModel):
    request_id: str
    original_query: str
    input_mode: str
    input_interpretation: InputInterpretation
    query_complexity: str
    filters_applied: dict
    total_studies_analyzed: int
    data_retrieval_strategy: str
    api_calls: list[APICallRecord]
    stage_timings: dict[str, float]
    api_version: str
    data_refresh: str
    notes: list[str] = []
    limitations: list[str] = []
    warnings: list[str] = []
    source: str = "clinicaltrials.gov"


class PipelineResponse(BaseModel):
    visualizations: list[VisualizationSpec]
    meta: ResponseMeta


class ErrorResponse(BaseModel):
    error: str
    message: str
    suggestion: str | None = None
    details: dict = {}
