"""Stage 1 output: semantic query intent (not raw API params).

The LLM produces a QueryIntent; deterministic code executes it. Data
requirements are separated from analysis tasks via task_data_map so that
several tasks sharing the same data don't trigger redundant API calls.
"""

from typing import Literal

from pydantic import BaseModel

# The 7 visualization categories — shared with VisualizationSpec.type_category.
VizCategory = Literal[
    "categorical",
    "temporal",
    "relational",
    "spatial",
    "matrix",
    "hierarchical",
    "distribution",
]


class AggregationSpec(BaseModel):
    group_by: list[str]  # StudyRecord field names
    metric: Literal["count", "sum", "collect", "unique_count"]
    metric_field: str | None = None
    sort_by: str | None = None
    time_granularity: Literal["year", "month", "quarter"] | None = None
    output_mode: Literal["aggregated", "raw_records", "edge_list"] = "aggregated"


class ExtractionSpec(BaseModel):
    needed: bool = False
    source_field: str = "excerpt"
    extract_as: str = ""
    extraction_prompt: str = ""
    expected_type: Literal["str", "number", "list[str]"] = "str"


class DataRequirement(BaseModel):
    requirement_id: str
    retrieval_strategy: Literal[
        "study_search", "study_detail", "field_stats", "combined"
    ]
    search_params: dict
    filter_params: dict
    entity_tag: str | None = None


class AnalysisTask(BaseModel):
    task_id: str
    description: str
    aggregation: AggregationSpec
    extraction: ExtractionSpec | None = None
    candidate_viz_categories: list[VizCategory]
    depends_on: str | None = None


class QueryIntent(BaseModel):
    original_query: str
    query_complexity: Literal["simple", "compound", "comparative"]
    data_requirements: list[DataRequirement]
    tasks: list[AnalysisTask]
    task_data_map: dict[str, list[str]]  # task_id -> [requirement_id, ...]
    requires_inference: bool = False
    inference_warning: str | None = None
