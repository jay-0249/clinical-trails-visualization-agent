# ClinicalTrials.gov Query-to-Visualization Agent

An AI-enabled backend service that converts natural-language questions about clinical trials into structured visualization specifications, backed by live data from the ClinicalTrials.gov API.

## Quick Start

```bash
# Clone and set up
git clone <repo>
cd ct-viz-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — add your OpenAI API key

# Run
uvicorn app.main:app --port 8000

# Verify
curl http://localhost:8000/health
```

### Configuration (`.env`)

```bash
OPENAI_API_KEY=your-key
LLM_MODEL_QUERY_ANALYZER=gpt-4o-2024-08-06   # Stage 1: planning
LLM_MODEL_VIZ_GENERATOR=gpt-5.4-nano         # Stage 4: viz spec
LLM_MODEL_EXTRACTOR=gpt-4o-mini              # Stage 2.5: extraction (v2)
CT_API_BASE_URL=https://clinicaltrials.gov/api/v2
CT_API_PAGE_SIZE=1000
CT_API_MAX_PAGES=10
CT_API_TIMEOUT_SECONDS=30
CT_API_RATE_LIMIT_DELAY=1.2
LOG_LEVEL=INFO
```

Each LLM stage has its own configurable model. `LLM_MODEL_QUERY_ANALYZER` is pinned to the dated snapshot `gpt-4o-2024-08-06` (some API keys have snapshot access but not the bare `gpt-4o` alias). Real environment variables override `.env`.

## How It Works

The system runs a 4-stage pipeline for each request:

```
User query → [Stage 1: Query Analysis] → [Stage 2: Data Retrieval] → [Stage 3: Aggregation] → [Stage 4: Viz Generation] → Response
                   LLM                        Code                        Code                      LLM
```

**Stage 1 (LLM):** Interprets the natural-language query into a structured `QueryIntent` — what data to fetch, how to aggregate it, what visualization categories fit. The prompt includes valid API enums and field names, so the LLM operates within validated constraints.

**Stage 2 (Code):** Translates the intent into ClinicalTrials.gov API calls. Handles pagination, rate limiting, retry, and normalizes raw responses into typed `StudyRecord` objects immediately.

**Stage 3 (Code):** A single generic aggregation function with three output modes — `aggregated` (group-by + metric), `raw_records` (for distributions), `edge_list` (for network graphs). No field-specific branching; the same function handles any dimension.

**Stage 4 (LLM):** Takes the aggregated data and produces a visualization specification with type, encoding, and rendering hints. The viz type is an open string (not an enum), so the system can recommend any chart type — bar, heatmap, sunburst, chord diagram — without code changes.

LLM calls: exactly 2 per request, each with an independently configurable model (Stage 1: gpt-4o-2024-08-06 for planning, Stage 4: gpt-5.4-nano for formatting). Everything between is deterministic.

**Stack:** Python 3.11+, FastAPI, Pydantic v2, pandas, httpx (async), OpenAI SDK

---

## API Reference

### POST /api/v1/query

**Request:**

```json
{
  "query": "How are Pembrolizumab trials distributed across phases?",
  "input_mode": "supplement",
  "drug_name": "Pembrolizumab",
  "condition": null,
  "sponsor": null,
  "trial_phase": null,
  "trial_status": null,
  "country": null,
  "start_year": null,
  "end_year": null,
  "include_citations": false,
  "max_citations_per_group": 5,
  "max_studies": 5000,
  "viz_category_preference": null
}
```

| Field                     | Type   | Required | Description                                               |
| ------------------------- | ------ | -------- | --------------------------------------------------------- |
| `query`                   | string | Yes      | Natural language question (min 3 chars)                   |
| `input_mode`              | string | No       | `"supplement"` (default), `"override"`, or `"query_only"` |
| `drug_name`               | string | No       | Intervention/drug name                                    |
| `condition`               | string | No       | Disease/condition                                         |
| `sponsor`                 | string | No       | Sponsor organization                                      |
| `trial_phase`             | string | No       | Phase filter, validated against API enums                 |
| `trial_status`            | string | No       | Status filter, validated against API enums                |
| `country`                 | string | No       | Country for geographic filtering                          |
| `start_year`              | int    | No       | Recorded in metadata; see Limitations (1990-2030)         |
| `end_year`                | int    | No       | Recorded in metadata; see Limitations (1990-2030)         |
| `include_citations`       | bool   | No       | Include deep citations per data point (default: false)    |
| `max_citations_per_group` | int    | No       | Cap citations per group (default: 5, max: 50)             |
| `max_studies`             | int    | No       | Safety cap on total records fetched (default: 5000)       |
| `viz_category_preference` | string | No       | Hint for preferred viz category                           |

**Input Modes:**

- `supplement` (default) — Query is primary, structured params confirm and augment. Conflicts: params win, logged.
- `override` — Params are the sole filter source. Query only provides analysis intent.
- `query_only` — Ignore all structured params. Everything from the natural language query.

**Response:**

```json
{
  "visualizations": [
    {
      "task_id": "task_1",
      "description": "Bar chart chosen: single categorical dimension with 6 unique values",
      "type": "bar_chart",
      "type_category": "categorical",
      "title": "Phase Distribution of Pembrolizumab Trials",
      "encoding": {
        "category": { "field": "phase_label" },
        "value": { "field": "value" }
      },
      "data": [
        { "phase_label": "Phase 1", "value": 45 },
        { "phase_label": "Phase 2", "value": 89 },
        { "phase_label": "Phase 3", "value": 41 }
      ],
      "rendering_hints": {
        "color_scheme": "sequential_blue",
        "sort_order": "descending",
        "orientation": "vertical"
      },
      "citations": null
    }
  ],
  "meta": {
    "request_id": "a1b2c3d4-...",
    "original_query": "How are Pembrolizumab trials distributed across phases?",
    "input_mode": "supplement",
    "input_interpretation": {
      "input_mode": "supplement",
      "from_query": { "req1": { "query.intr": "Pembrolizumab" } },
      "from_params": { "drug_name": "Pembrolizumab" },
      "conflicts": [],
      "resolution": "Query is primary; structured params confirm/add (supplement)."
    },
    "query_complexity": "simple",
    "filters_applied": { "query.intr": "Pembrolizumab" },
    "total_studies_analyzed": 175,
    "data_retrieval_strategy": "study_search",
    "api_calls": [
      {
        "endpoint": "/studies",
        "params": { "query.intr": "Pembrolizumab", "pageSize": 1000 },
        "http_status": 200,
        "record_count": 175,
        "duration_ms": 340
      }
    ],
    "stage_timings": {
      "query_analysis": 2100,
      "data_retrieval": 450,
      "aggregation_task_1": 12,
      "viz_generation_task_1": 1800
    },
    "api_version": "2.0.5",
    "data_refresh": "2026-07-21T09:00:05",
    "notes": [],
    "limitations": [],
    "warnings": [],
    "source": "clinicaltrials.gov"
  }
}
```

**Error Response** (structured hint validation, HTTP 400; errors are returned under FastAPI's `detail`):

```json
{
  "detail": {
    "error": "invalid_phase",
    "message": "trial_phase 'Phase3' is not a valid phase.",
    "valid_values": ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]
  }
}
```

### GET /health

```json
{
  "status": "ok",
  "api_version": "2.0.5",
  "cache_loaded": true,
  "data_refresh": "2026-07-21T09:00:05"
}
```

---

## Visualization Type System

The system supports 7 visualization categories. `type` is an open string (any chart name), `type_category` constrains the encoding structure so a frontend can render reliably:

| Category     | Chart types                 | Encoding contract          |
| ------------ | --------------------------- | -------------------------- |
| categorical  | bar, pie, treemap, lollipop | `{category, value}`        |
| temporal     | line, area, gantt           | `{time, value, series}`    |
| relational   | network, chord, sankey      | `{source, target, weight}` |
| spatial      | choropleth, bubble map      | `{location, value}`        |
| matrix       | heatmap                     | `{x, y, color}`            |
| hierarchical | sunburst, radial tree       | `{levels[], value}`        |
| distribution | histogram, box plot         | `{value, bins}`            |

The frontend needs one renderer per category (7 total), not per chart type.

---

## Supported Query Types

The system handles diverse query patterns through a single generic pipeline — no query-type-specific code paths:

- **Distributions:** "How are [drug] trials distributed across phases?"
- **Time trends:** "How has the number of trials for [condition] changed per year?"
- **Comparisons:** "Compare phases for [Drug A] vs [Drug B] trials"
- **Geographic:** "Which countries have the most recruiting trials for [condition]?"
- **Networks:** "Show a network of sponsors and drugs for [condition] trials"
- **Hierarchical:** "Break down trials by sponsor type, then sponsor, then drug"
- **Distributions:** "What is the enrollment distribution for Phase 3 [condition] trials?"

---

## Key Design Decisions

**1. Minimize LLM calls (2 per request)**

The LLM interprets (Stage 1) and formats (Stage 4). Data retrieval, normalization, and aggregation are deterministic code. This reduces latency, cost, and hallucination surface.

**2. Generic aggregation over hardcoded patterns**

A single `aggregate()` function handles any combination of fields and metrics. The LLM describes _what_ to aggregate via a spec; code executes it. The aggregator was tested with fields not in any example query to prove generality.

**3. Open visualization types with constrained encoding**

`type` is a free string so the system can recommend any chart without code changes. `type_category` (7 values) constrains the encoding structure so frontends render predictably.

**4. Input modes for explicit query/param combination**

Rather than guessing how to merge natural language with structured params, the caller declares intent: `supplement`, `override`, or `query_only`. Every mode produces correct results for its contract. Conflicts are detected and logged.

**5. Validate against live API enums, not hardcoded lists**

At startup, the service fetches valid enums from `/studies/enums`. Validation runs against this live set. Hardcoded fallbacks exist only for startup resilience and are never used by pipeline code.

**6. Normalize early, work on typed records**

Raw API responses are converted to flat `StudyRecord` objects immediately upon retrieval. All downstream code works on clean, typed data — never raw JSON.

**7. Per-stage model configuration (diagnostic-driven)**

Each LLM stage has its own configurable model (`LLM_MODEL_QUERY_ANALYZER`, `LLM_MODEL_VIZ_GENERATOR`, `LLM_MODEL_EXTRACTOR`). The Stage 4 model (`gpt-5.4-nano`) was chosen with a 15-run diagnostic: it emitted `rendering_hints` on 3/3 runs versus `gpt-4o-mini`'s 1/9, at the smallest/cheapest tier, while picking the correct chart type every time. A defensive code fallback injects a default `color_scheme` if a future model regresses.

See `docs/DECISIONS.md` for the complete decision log with tradeoffs.

---

## Architecture

```
Startup:
  → /studies/enums → cache valid enums
  → /studies/metadata → cache field metadata
  → /version → cache API version

Per request:
  ┌─────────────────────────────────────────────────────┐
  │ POST /api/v1/query                                  │
  │                                                     │
  │ 1. Validate structured hints (pre-LLM)              │
  │ 2. Stage 1: Query Analysis (LLM)                    │
  │    → QueryIntent with DataRequirements + Tasks      │
  │ 3. Validate intent against enums + fields            │
  │ 4. Merge structured hints (mode-aware)               │
  │ 5. Stage 2: Data Retrieval (code)                   │
  │    → Paginated API calls → StudyRecords             │
  │ 6. Stage 3: Aggregation (code)                      │
  │    → Generic group-by / edge-list / raw-records     │
  │ 7. Stage 4: Viz Spec Generation (LLM)               │
  │    → VisualizationSpec with encoding + hints        │
  │                                                     │
  │ Response: visualizations[] + full audit metadata    │
  └─────────────────────────────────────────────────────┘
```

---

## Traceability

Every response includes:

- `request_id` — UUID linking to all structured log entries
- `api_calls` — every ClinicalTrials.gov API call with params, status, duration
- `input_interpretation` — what was extracted from query vs params, any conflicts
- `stage_timings` — millisecond timing per pipeline stage
- `filters_applied` — exact API parameters used
- `limitations` / `warnings` — truncation, sampling, assumptions

Logs are structured JSON with `request_id` on every entry, enabling full request reconstruction from logs alone.

---

## Limitations and Future Improvements

**Current limitations:**

- Free-text extraction (Stage 2.5) is architected but not implemented — queries requiring data from study descriptions or eligibility criteria (e.g., dosage, endpoints) won't produce results.
- `start_year`/`end_year` hints are recorded in metadata but not applied as hard API filters — CT.gov v2 has no simple year-range parameter, so the year dimension is handled by temporal aggregation (`group_by=[start_year]`), not by filtering.
- The `field_stats` and `study_detail` retrieval strategies are best-effort: `field_stats` (a v2 pre-aggregation strategy) isn't wired into the record-based aggregator, so when the planner selects it the retriever falls back to `study_search` (capped sample, noted in metadata). `study_search` is the fully exercised path.
- Dependent queries (task B depends on task A results) are architected but not implemented.
- No typo/synonym handling — "Keytruda" won't resolve to "Pembrolizumab".

**What I would improve with more time:**

- Implement the `field_stats` strategy end-to-end for efficient broad distribution queries (100K+ matches without capping).
- Apply `start_year`/`end_year` as real filters (via the CT.gov advanced query syntax or post-retrieval filtering).
- Add entity normalization via LLM (drug synonyms, condition aliases).
- Add a simple demo UI (HTML + a charting lib) that renders the viz specs.
- Add a caching layer for repeated API queries within a time window.
- Implement the free-text extraction pipeline with batching for large result sets.

---

## AI Tools Used

**Design phase:** Claude (Anthropic) for pair-designing the system architecture, data models, pipeline stages, prompt templates, and test scenarios. All design decisions were deliberated through conversation — the architecture reflects considered tradeoffs, not generated boilerplate.

**Implementation:** Claude Code for building the code phase-by-phase from detailed design documents. Each phase was reviewed and approved before proceeding. The system was designed to prevent overfitting: no pipeline code references specific drug names, conditions, or query phrases.

**LLM integration:** The pipeline uses the **OpenAI SDK directly, not LangChain**. Strict structured outputs can't represent the free-form `dict` fields in `DataRequirement` (search/filter params), so each LLM stage uses JSON mode + Pydantic validation with a one-shot corrective retry — more robust and transparent than a framework abstraction for this use case.

**Validation:** Automated tests (pytest) at every phase, cumulative suite always passing. Anti-overfit verification: queries not in the problem statement examples, all producing valid results without code changes. Live API integration tests against ClinicalTrials.gov.

**What was designed deliberately:**

- Pipeline architecture (structured planning over ReAct, minimizing LLM calls)
- Input mode system (supplement/override/query_only with conflict detection)
- Open visualization type system with category-based encoding contracts
- Generic aggregation with 3 output modes
- Two-layer validation (validator + aggregator runtime guards) and defensive guardrails (param whitelist, encoding-key normalization, model fallbacks)
- Structured logging and traceability design

**What was generated and adapted:**

- Individual module implementations from design specs
- Test fixtures and boilerplate
- Date parsing regex patterns

---

## Example Runs

See `examples/` for 5 complete request-response pairs:

1. `example_1_phase_distribution.json` — categorical (bar chart)
2. `example_2_time_trend.json` — temporal (line chart)
3. `example_3_comparison.json` — comparative (grouped bar)
4. `example_4_geographic.json` — spatial (choropleth)
5. `example_5_network.json` — relational (sponsor-drug network)

---

## Project Structure

```
app/
  main.py                    # FastAPI endpoint + startup
  config.py                  # Settings from .env (per-stage models)
  schemas/
    request.py               # QueryRequest
    response.py              # PipelineResponse, VisualizationSpec, ResponseMeta
    intent.py                # QueryIntent, AggregationSpec, DataRequirement
    trial_record.py          # StudyRecord, PipelineContext, APICallRecord
  pipeline/
    orchestrator.py           # Pipeline runner + input-mode merge + error mapping
    query_analyzer.py         # Stage 1: NL → QueryIntent (LLM)
    data_retriever.py         # Stage 2: DataRequirement → API calls → StudyRecords
    aggregator.py             # Stage 3: Generic aggregation (3 modes)
    viz_generator.py          # Stage 4: Data → VisualizationSpec (LLM)
  services/
    ct_client.py              # ClinicalTrials.gov API client + normalization
    reference_cache.py        # Startup enum/metadata/version cache
  prompts/
    query_analyzer.py         # Stage 1 prompt template + builder
    viz_generator.py          # Stage 4 prompt template + builder
  utils/
    date_parser.py            # Messy date normalization
    validators.py             # Intent + hint validation
    logger.py                 # Structured JSON logging
    helpers.py                # safe_get utility
tests/
  test_schemas.py
  test_date_parser.py         # + logger/config
  test_ct_client.py
  test_reference_cache.py
  test_validators.py
  test_aggregator.py
  test_query_analyzer.py      # Stage 1 (integration)
  test_viz_generator.py       # Stage 4 (integration)
  test_orchestrator.py        # merge/error (hermetic) + e2e (integration)
  test_pipeline_e2e.py        # endpoint end-to-end (integration)
  test_anti_overfit.py        # anti-overfit gate (integration)
examples/
  example_1_phase_distribution.json
  example_2_time_trend.json
  example_3_comparison.json
  example_4_geographic.json
  example_5_network.json
```

---

## Running Tests

```bash
# All hermetic tests (no network, no LLM) — the default
pytest tests/ -v

# Live integration tests (real API + LLM; needs OPENAI_API_KEY + network)
pytest tests/ -v -m integration

# Specific component
pytest tests/test_aggregator.py -v
```

---

## Anti-Overfit Verification

These queries are NOT in the problem statement examples. All must produce valid responses without any code changes:

```bash
# Run as a batch against a running server
BASE="http://localhost:8000/api/v1/query"
pass=0; fail=0

queries=(
  '{"query":"How are Trastuzumab trials distributed across phases?"}'
  '{"query":"Show trial trends for Crohn'\''s disease since 2010"}'
  '{"query":"What is the enrollment distribution for Phase 3 cancer trials?","trial_phase":"PHASE3"}'
  '{"query":"Show how sponsor types have changed over time for diabetes"}'
  '{"query":"Break down breast cancer trials by sponsor type, then by specific sponsor, then by drug"}'
  '{"query":"Which countries have the most recruiting trials for HIV?"}'
  '{"query":"Which drugs frequently co-occur in combination studies for lymphoma?"}'
  '{"query":"Show Phase 3 Pembrolizumab trials by phase AND their geographic distribution"}'
  '{"query":"show me the data","drug_name":"Pembrolizumab","input_mode":"override"}'
  '{"query":"What are the most common study types for Alzheimer trials?"}'
)

for i in "${!queries[@]}"; do
  result=$(curl -s -X POST $BASE -H 'Content-Type: application/json' \
    -d "${queries[$i]}" | python3 -c \
    "import sys,json; d=json.load(sys.stdin); print('PASS' if d.get('visualizations') or d.get('detail') else 'FAIL')" 2>/dev/null)
  echo "Test $((i+1))/10: $result"
  if [ "$result" = "PASS" ]; then ((pass++)); else ((fail++)); fi
done

echo "Results: $pass passed, $fail failed"
```

These cover unfamiliar drugs (Trastuzumab), unfamiliar conditions (Crohn's, HIV, lymphoma, Alzheimer's), unusual viz types (histogram, heatmap, hierarchical, network), multi-part queries, vague queries with override mode, and unseen fields (study_type).

---

## Quick Verification Commands

```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Simple query
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "How are Pembrolizumab trials distributed across phases?"}' \
  | python3 -m json.tool

# With structured hints
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "trials by phase", "drug_name": "Pembrolizumab", "trial_status": "RECRUITING"}' \
  | python3 -m json.tool

# Error: invalid enum (expect 400)
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "trials", "trial_phase": "PHASE99"}' \
  | python3 -m json.tool

# Error: query too short (expect 422)
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "hi"}' | python3 -m json.tool

# With deep citations
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Pembrolizumab trials by phase", "include_citations": true, "max_citations_per_group": 3}' \
  | python3 -m json.tool
```
