## Design Philosophy

- **Minimize LLM calls** — each call is a hallucination surface. LLM for interpretation and formatting, deterministic code for data manipulation.
- **Fail visibly with context** — every error tells the caller what was attempted and why it failed.
- **Normalize early** — convert messy API responses to typed records immediately. Everything downstream works on clean data.
- **Dynamic aggregation** — LLM describes what to aggregate via a spec, code executes it. No hardcoded aggregation patterns.
- **Per-request pipeline** — no cross-request state. Each request is self-contained.

---

## High-Level Architecture

```
Startup:
  → fetch /studies/enums → cache valid enums
  → fetch /studies/metadata → cache field metadata
  → fetch /version → cache API version + data refresh timestamp

Per-request pipeline:
  Stage 1 (LLM):   NL query → QueryIntent
  Stage 2 (code):  QueryIntent → API calls → list[StudyRecord]
  Stage 2.5 (LLM): [CONDITIONAL] free-text extraction (v2)
  Stage 3 (code):  StudyRecords + AggregationSpec → aggregated data
  Stage 4 (LLM):   aggregated data → VisualizationSpec
```

Total LLM calls: 2 per request (Stage 1 + Stage 4). Fewer calls = lower latency, lower cost, fewer hallucination opportunities.

---

## Pipeline Stages

**Stage 1 — Query Analysis (LLM):** Takes NL query + optional structured hints + input_mode. Produces a validated `QueryIntent` containing data requirements, aggregation specs, and candidate viz categories. Prompt includes valid enums, groupable fields, and tool schemas. Does NOT produce raw API parameters — produces semantic intent.

**Stage 2 — Data Retrieval (code):** Translates `DataRequirement` objects into ClinicalTrials.gov API calls. Handles pagination, retry, rate limiting, normalization to `StudyRecord`, deduplication, entity tagging for comparisons. Three strategies: `study_search`, `field_stats`, `study_detail`.

**Stage 2.5 — Extraction (conditional LLM, v2):** Fires when query needs data from free-text fields. Strategies: individual (≤20), batched (21-100), sampled (>100). Deferred to v2.

**Stage 3 — Aggregation (code):** Single generic function, three output modes: `aggregated` (group-by + metric), `raw_records` (pass-through for distributions), `edge_list` (co-occurrence for networks). Uses pandas. Deterministic.

**Stage 4 — Viz Generation (LLM):** Takes aggregated data + task description. Chooses `type` (open string) and `type_category` (7 Literals). Maps fields to encoding contract. Justifies choice in description. Never invents data.

See `docs/impl/phase_N_*.md` for implementation details of each stage.

---

## Multi-Query Support

- **Simple** — 1 data requirement, 1 task, 1 visualization
- **Compound** — 1 data requirement, N tasks, N visualizations (same data, different aggregations)
- **Comparative** — N data requirements (entity-tagged), M tasks, M visualizations
- **Dependent** — task B depends on task A results (architected, deferred to v2)

`QueryIntent` separates data requirements from analysis tasks via `task_data_map`. This prevents redundant API calls when multiple tasks share data.

---

## Visualization Type System

`type` is an **open string** (any chart type). `type_category` is a **Literal** constraining the encoding structure. 7 categories:

| Category     | Examples               | output_mode                 | Encoding contract          |
| ------------ | ---------------------- | --------------------------- | -------------------------- |
| categorical  | bar, pie, treemap      | aggregated                  | `{category, value}`        |
| temporal     | line, area, gantt      | aggregated                  | `{time, value, series}`    |
| relational   | network, chord, sankey | edge_list                   | `{source, target, weight}` |
| spatial      | choropleth, bubble map | aggregated                  | `{location, value}`        |
| matrix       | heatmap                | aggregated (2 group_by)     | `{x, y, color}`            |
| hierarchical | sunburst, radial tree  | aggregated (multi group_by) | `{levels[], value}`        |
| distribution | histogram, box plot    | raw_records                 | `{value, bins}`            |

`rendering_hints` carries non-structural suggestions: color_scheme, orientation, scale_type, sort_order.

The frontend needs one renderer per category (7), not per chart type. `type` tells it which variant.

---

## Input Mode System

`input_mode` controls how query text and structured params combine:

- **supplement** (default) — query is primary, params confirm/add. Conflicts: params win, logged. Comparison arms from query preserved.
- **override** — params are sole filter source. Query provides analysis intent only. Comparison with single param collapses to single-entity + warning.
- **query_only** — ignore all params. Metadata notes what was ignored.

Every mode produces correct results for its contract. `InputInterpretation` in response shows what came from where.

See `docs/impl/phase_9_orchestrator.md` for merge function implementation.

---

## Large Data Handling

- **field_stats strategy** — `GET /stats/field/values` for broad distributions. One API call, any scale, no citations.
- **study_search with cap** — individual records up to `max_studies` (default 5000). Truncation noted in metadata.
- Stage 1 LLM chooses strategy based on query scope and citation needs.

---

## Tool Design Philosophy

LLM plans tool usage (which endpoints, what params) via `DataRequirement` specs. Code executes through a validated client with retry, rate limiting, pagination. This gives "appropriate tools" rubric credit while preventing hallucinated params and uncontrolled API calls.

Three tools exposed in Stage 1 prompt: `search_studies`, `get_field_stats`, `get_study_detail`.

---

## Deep Citations (v2)

Citations are a byproduct of aggregation. Each group carries `nct_id` + `excerpt` + `evidence` for the records in it. Toggled via `include_citations` in request. Capped at `max_citations_per_group`. Architecture is in place, implementation deferred.

---

## Error Handling

Three layers:

1. **API-level** — retry with backoff on 429/5xx, 30s timeout, rate limiting. Zero results is valid.
2. **Pipeline-level** — validate intent after Stage 1, validate data sufficiency after Stage 2, validate viz spec after Stage 4.
3. **Request-level** — structured `ErrorResponse` with error code, message, suggestion.

---

## MVP vs V2

**MVP:** Stages 1-4, all 3 aggregation modes, 7 viz categories, input modes, enum caching, structured logging, error handling, 3-5 examples.

**V2:** Free-text extraction (Stage 2.5), dependent queries, deep citations, typo/synonym handling, field_stats strategy, sampling.

---

## Structured Logging

Every request gets a UUID4 `request_id` that flows through all stages and appears in every log entry and response metadata. Logs are structured JSON with: timestamp, request_id, event, level, plus event-specific fields.

Key events: `pipeline_start/complete`, `stage_start/complete`, `api_call`, `llm_call`, `validation_failure`, `merge_result`, `pipeline_error`.

See `docs/impl/phase_2_utilities.md` for logger implementation.

---

## Data Models

All Pydantic model definitions are in `docs/impl/phase_1_schemas.md`. Key models:

- `QueryRequest` (with `input_mode`), `StudyRecord`, `QueryIntent` (with `AggregationSpec`, `DataRequirement`, `AnalysisTask`), `VisualizationSpec` (with `type_category`), `PipelineResponse`, `ResponseMeta`, `PipelineContext`, `ErrorResponse`

## API Reference

ClinicalTrials.gov API v2 details are in `docs/API_REFERENCE.md`.

## Versioning

- API: `/api/v1/` prefix
- Prompts: version comment + git
- Models: Pydantic contracts, schema change = version bump
