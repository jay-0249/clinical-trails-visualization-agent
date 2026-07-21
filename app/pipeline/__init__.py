"""Pipeline stages: query analysis, retrieval, aggregation, viz generation."""

from app.pipeline.aggregator import AggregationError, aggregate

__all__ = ["AggregationError", "aggregate"]
