**Files to create:**

- `app/schemas/request.py`
- `app/schemas/response.py`
- `app/schemas/intent.py`
- `app/schemas/trial_record.py`

**Reference:** `docs/DESIGN.md` Data Models section for full field definitions.

---

## request.py — QueryRequest

```python
from pydantic import BaseModel, Field
from typing import Literal

class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, description="Natural language question about clinical trials")

    input_mode: Literal["supplement", "override", "query_only"] = Field(
        "supplement",
        description="How to combine query text and structured params"
    )

    drug_name: str | None = Field(None, description="Intervention/drug name")
    condition: str | None = Field(None, description="Disease/condition")
    sponsor: str | None = Field(None, description="Sponsor organization")
    trial_phase: str | None = Field(None, description="Phase filter, validated against API enums")
    trial_status: str | None = Field(None, description="Status filter, validated against API enums")
    country: str | None = Field(None, description="Country for geographic filtering")
    start_year: int | None = Field(None, ge=1990, le=2030)
    end_year: int | None = Field(None, ge=1990, le=2030)

    include_citations: bool = False
    max_citations_per_group: int = Field(5, ge=1, le=50)
    max_studies: int = Field(5000, ge=1, le=10000)
    viz_category_preference: str | None = None
```

## intent.py — QueryIntent and related

```python
class AggregationSpec(BaseModel):
    group_by: list[str]                    # field names on StudyRecord
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
    retrieval_strategy: Literal["study_search", "study_detail", "field_stats", "combined"]
    search_params: dict
    filter_params: dict
    entity_tag: str | None = None

class AnalysisTask(BaseModel):
    task_id: str
    description: str
    aggregation: AggregationSpec
    extraction: ExtractionSpec | None = None
    candidate_viz_categories: list[Literal[
        "categorical", "temporal", "relational", "spatial",
        "matrix", "hierarchical", "distribution"
    ]]
    depends_on: str | None = None

class QueryIntent(BaseModel):
    original_query: str
    query_complexity: Literal["simple", "compound", "comparative"]
    data_requirements: list[DataRequirement]
    tasks: list[AnalysisTask]
    task_data_map: dict[str, list[str]]
    requires_inference: bool = False
    inference_warning: str | None = None
```

## trial_record.py — StudyRecord, PipelineContext

```python
class StudyRecord(BaseModel):
    nct_id: str
    title: str
    status: str
    phases: list[str]
    phase_label: str
    conditions: list[str]
    interventions: list[str]
    intervention_types: list[str]
    sponsor_name: str | None
    sponsor_class: str | None
    start_year: int | None
    start_month: int | None
    completion_year: int | None
    countries: list[str]
    cities: list[str]
    enrollment: int | None
    study_type: str | None
    excerpt: str
    source_query: str
    entity_tag: str | None = None

class FieldStatRecord(BaseModel):
    field_name: str
    field_value: str
    count: int

class APICallRecord(BaseModel):
    endpoint: str
    params: dict
    timestamp: str
    record_count: int
    http_status: int
    duration_ms: int

class PipelineContext(BaseModel):
    request_id: str
    studies: dict[str, StudyRecord] = {}
    field_stats: list[FieldStatRecord] = []
    enums: dict[str, list[str]] = {}
    api_version: str = ""
    last_data_refresh: str = ""
    api_calls_made: list[APICallRecord] = []
    notes: list[str] = []
    limitations: list[str] = []
    warnings: list[str] = []
    conflicts: list[str] = []
    stage_timings: dict[str, float] = {}

    def add_studies(self, records, entity_tag=None): ...
    def get_studies_by_tags(self, tags) -> list[StudyRecord]: ...
    def get_all_studies(self) -> list[StudyRecord]: ...
    def add_note(self, note): self.notes.append(note)
    def add_limitation(self, lim): self.limitations.append(lim)
    def add_warning(self, warn): self.warnings.append(warn)
    def add_conflict(self, c): self.conflicts.append(c)
```

## response.py — VisualizationSpec, ResponseMeta, PipelineResponse

```python
class InputInterpretation(BaseModel):
    input_mode: str
    from_query: dict = {}
    from_params: dict = {}
    conflicts: list[str] = []
    resolution: str = ""
    ignored_params: dict = {}

class VisualizationSpec(BaseModel):
    task_id: str
    description: str
    type: str                          # OPEN string
    type_category: Literal[
        "categorical", "temporal", "relational", "spatial",
        "matrix", "hierarchical", "distribution"
    ]
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
```

---

## Test: `tests/test_schemas.py`

See `tests/test_schemas.md` for all test cases.

<!-- Create tests for:

- QueryRequest validation (min_length, input_mode, field constraints)
- AggregationSpec output_mode values
- VisualizationSpec type_category Literal validation
- All models round-trip (construct → dump → validate)
- Optional fields default to None
- Invalid values rejected -->
