"""Pipeline stages: query analysis, retrieval, aggregation, viz generation."""

from app.pipeline.aggregator import AggregationError, aggregate
from app.pipeline.data_retriever import fetch_data
from app.pipeline.orchestrator import (
    build_error_response,
    build_meta,
    execute,
    merge_and_validate,
)
from app.pipeline.query_analyzer import QueryAnalysisError, analyze
from app.pipeline.viz_generator import VizGenerationError, generate

__all__ = [
    "AggregationError",
    "aggregate",
    "fetch_data",
    "build_error_response",
    "build_meta",
    "execute",
    "merge_and_validate",
    "QueryAnalysisError",
    "analyze",
    "VizGenerationError",
    "generate",
]
