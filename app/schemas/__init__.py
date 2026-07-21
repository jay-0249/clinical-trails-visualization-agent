"""Pydantic contracts shared across every pipeline stage."""

from app.schemas.intent import (
    AggregationSpec,
    AnalysisTask,
    DataRequirement,
    ExtractionSpec,
    QueryIntent,
    VizCategory,
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

__all__ = [
    "AggregationSpec",
    "AnalysisTask",
    "DataRequirement",
    "ExtractionSpec",
    "QueryIntent",
    "VizCategory",
    "QueryRequest",
    "ErrorResponse",
    "InputInterpretation",
    "PipelineResponse",
    "ResponseMeta",
    "VisualizationSpec",
    "APICallRecord",
    "FieldStatRecord",
    "PipelineContext",
    "StudyRecord",
]
