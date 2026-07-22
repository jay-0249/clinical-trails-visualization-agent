# ClinicalTrials.gov Query-to-Visualization Agent

An AI-enabled backend service that converts natural-language questions about clinical trials into structured visualization specifications, backed by live data from the ClinicalTrials.gov API.

**What if you could ask a question about clinical trials in plain English and get back a visualization spec ready for any frontend to render?**

"How are Pembrolizumab trials distributed across phases?" → A bar chart spec with real data from 175 trials.

"Show a network of sponsors and drugs for breast cancer" → A force-directed graph with 121 edges across 50 studies.

"Compare Pembrolizumab vs Nivolumab by phase" → A grouped bar chart with entity-tagged comparison arms.

This is a backend service that interprets natural-language questions about clinical trials, fetches live data from ClinicalTrials.gov, and produces structured visualization specifications — complete with encoding contracts, rendering hints, and optional source citations that trace every data point back to its origin trial.

> ## Release 1 (stable submission)
>
> This is the **stable submission** — the full pipeline (Phases 0–12) plus
> **V2.1 deep citations** and **V2.2 year filtering**, deployed and verified live.
> `release-1` is the stable submission branch; ongoing development (V2.3+)
> continues on `main`.

---

## Quick Start

```bash
git clone <repo>
cd ct-viz-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your OpenAI API key
uvicorn app.main:app --port 8000
```

Then:

```bash
curl http://localhost:8000/health
```

```json
{ "status": "ok", "api_version": "2.0.5", "cache_loaded": true }
```

Your first query:

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "How are Pembrolizumab trials distributed across phases?"}' \
  | python3 -m json.tool
```

---

## Live Demo

**Deployed at:** https://https://clinical-trails-visualization-agent.onrender.com _(replace with actual URL)_

> Render free tier sleeps after inactivity. First request takes ~30-60s to wake. After that, queries take ~13-16s (two LLM calls + live ClinicalTrials.gov API fetch).

```bash
# Try these against the live endpoint:

# Phase distribution
curl -s -X POST https://https://clinical-trails-visualization-agent.onrender.com/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "How are Pembrolizumab trials distributed across phases?"}'

# With source citations
curl -s -X POST https://https://clinical-trails-visualization-agent.onrender.com/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Pembrolizumab trials by phase", "include_citations": true}'

# Sponsor-drug network
curl -s -X POST https://https://clinical-trails-visualization-agent.onrender.com/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query": "Show a network of sponsors and drugs for breast cancer trials"}'
```

---

## The Problem

ClinicalTrials.gov has 500,000+ studies. The data is public but the API returns deeply nested JSON that requires domain knowledge to query effectively. Answering even a simple question — "how many Phase 3 cancer trials are recruiting in the US?" — means knowing the right API parameters, paginating through results, normalizing messy date formats, and aggregating across study records.

This service turns that into a single API call with a natural-language question.

## The Approach: A Structured Pipeline, Not a Chat Agent

Many AI systems would throw the question at an LLM and hope for the best. This one uses the LLM surgically — exactly twice per request — and does everything else with deterministic, testable code.

```
┌────────────────────────────────────────────────────────────┐
│  "How are Pembrolizumab trials distributed across phases?"  │
└─────────────────────────┬──────────────────────────────────┘
                          │
         ┌──────────────┴──────────────┐
         │  Stage 1: Query Analysis   │  ← LLM call #1
         │  NL → structured intent    │    Interprets the question
         │  (what to fetch, how to    │    into a machine-readable plan
         │   aggregate, what viz)     │
         └──────────────┬──────────────┘
                          │
         ┌──────────────┴──────────────┐
         │  Stage 2: Data Retrieval   │  ← Deterministic code
         │  ClinicalTrials.gov API    │    Pagination, retry, rate
         │  → normalized StudyRecords │    limiting, normalization
         └──────────────┬──────────────┘
                          │
         ┌──────────────┴──────────────┐
         │  Stage 3: Aggregation      │  ← Deterministic code
         │  Generic group-by engine   │    One function handles
         │  3 modes: aggregated,      │    any field, any metric
         │  raw_records, edge_list    │
         └──────────────┬──────────────┘
                          │
         ┌──────────────┴──────────────┐
         │  Stage 4: Viz Spec Gen     │  ← LLM call #2
         │  Data shape → chart type   │    Chooses the best viz,
         │  + encoding + hints        │    maps data to encoding
         └──────────────┬──────────────┘
                          │
         ┌──────────────┴──────────────┐
         │  Structured JSON response  │
         │  + full audit metadata     │
         └─────────────────────────────┘
```

Why only 2 LLM calls? Because each call is a hallucination surface. The LLM interprets (Stage 1) and formats (Stage 4). Everything between — API calls, data normalization, aggregation — is deterministic code that can be tested, debugged, and trusted.

---

## Project Structure

Every file has a single, clear responsibility:

```
ct-viz-agent/
│
├── app/
│   │
│   ├── main.py                     # FastAPI app with startup cache loading
│   │                                # POST /api/v1/query + GET /health
│   │
│   ├── config.py                   # Settings from .env via pydantic-settings
│   │                                # Per-stage LLM models, API timeouts, rate limits
│   │
│   ├── schemas/                    # Pydantic models — the contracts between everything
│   │   ├── request.py              #   QueryRequest: query + input_mode + structured hints
│   │   ├── response.py             #   PipelineResponse, VisualizationSpec, ResponseMeta
│   │   ├── intent.py               #   QueryIntent: what Stage 1 produces for Stage 2-4
│   │   └── trial_record.py         #   StudyRecord: normalized from CT.gov's nested JSON
│   │
│   ├── pipeline/                   # The 4-stage processing pipeline
│   │   ├── orchestrator.py         #   Chains all stages, manages context, handles errors
│   │   ├── query_analyzer.py       #   Stage 1: NL question → QueryIntent (LLM)
│   │   ├── data_retriever.py       #   Stage 2: QueryIntent → API calls → StudyRecords
│   │   ├── aggregator.py           #   Stage 3: StudyRecords → aggregated data (pandas)
│   │   └── viz_generator.py        #   Stage 4: data → VisualizationSpec (LLM)
│   │
│   ├── services/                   # External service integrations
│   │   ├── ct_client.py            #   ClinicalTrials.gov API v2 client
│   │   │                            #   Pagination, retry, rate limiting, normalization
│   │   └── reference_cache.py      #   Startup cache: enums, metadata, API version
│   │                                #   Validates against live API, not hardcoded values
│   │
│   ├── prompts/                    # LLM prompt templates (versioned via git)
│   │   ├── query_analyzer.py       #   Stage 1 prompt: reasoning framework + examples
│   │   └── viz_generator.py        #   Stage 4 prompt: encoding contracts + type selection
│   │
│   └── utils/                      # Shared utilities
│       ├── date_parser.py          #   Handles CT.gov's 4+ inconsistent date formats
│       ├── validators.py           #   Two-layer validation: pre-LLM + post-LLM
│       ├── logger.py               #   Structured JSON logging with request_id
│       └── helpers.py              #   safe_get() for nested dict access
│
├── tests/                          # 100+ tests across 7 files
│   ├── test_schemas.py             #   Model validation and round-trip tests
│   ├── test_date_parser.py         #   9 date format scenarios
│   ├── test_ct_client.py           #   11 normalization + 1 live API smoke test
│   ├── test_validators.py          #   14 validation scenarios
│   ├── test_aggregator.py          #   18 tests across 3 output modes
│   ├── test_pipeline_e2e.py        #   End-to-end integration tests
│   └── test_anti_overfit.py        #   13 unseen queries — the generality gate
│
├── examples/                       # 5 real query-response pairs
├── docs/                           # Design documents and decision log
│   ├── DESIGN.md                   #   Architecture overview
│   ├── API_REFERENCE.md            #   ClinicalTrials.gov API v2 details
│   ├── DECISIONS.md                #   Every implementation decision with tradeoffs
│   └── impl/                       #   Per-phase implementation specs
│
├── Dockerfile                      # Production-ready container
├── requirements.txt
├── .env.example                    # All configuration with defaults
└── Makefile                        # make install / make run / make test
```

---

## How a Query Flows Through the System

Let’s trace "Compare Pembrolizumab vs Nivolumab by phase" from input to output:

**Stage 1 (LLM — ~3s):** The query analyzer recognizes this as a _comparative_ query involving two drugs. It produces a `QueryIntent` with:

- 2 `DataRequirement` objects, each tagged: `entity_tag="Pembrolizumab"` and `entity_tag="Nivolumab"`
- 1 `AnalysisTask` with `group_by=["phase_label", "entity_tag"]`, `metric="count"`, `candidate_viz_categories=["categorical"]`
- `task_data_map` linking the task to both data requirements

The intent is validated against live API enums (is "PHASE3" a real phase?) and StudyRecord field names (is "phase_label" a real field?).

**Stage 2 (Code — ~6s):** Two separate API calls to ClinicalTrials.gov:

- `query.intr=Pembrolizumab` → fetches ~175 studies, normalizes each to a flat `StudyRecord`, tags with `entity_tag="Pembrolizumab"`
- `query.intr=Nivolumab` → fetches ~120 studies, tags with `entity_tag="Nivolumab"`

Studies appearing in both results get compound tags. Every API call is logged with endpoint, params, status code, record count, and duration.

**Stage 3 (Code — <100ms):** The generic aggregator groups all 295 studies by `[phase_label, entity_tag]` and counts:

```json
[
  {"phase_label": "Phase 1", "entity_tag": "Pembrolizumab", "count": 28},
  {"phase_label": "Phase 1", "entity_tag": "Nivolumab", "count": 19},
  {"phase_label": "Phase 2", "entity_tag": "Pembrolizumab", "count": 67},
  ...
]
```

If `include_citations=true`, each row also carries the `nct_id` + `excerpt` of the trials in that group.

**Stage 4 (LLM — ~3s):** The viz generator sees two categorical dimensions and picks `grouped_bar_chart`. It maps `phase_label` to the x-axis, `count` to y-axis, and `entity_tag` to the series. The response includes `rendering_hints` for colors and sort order.

The LLM cannot invent data — `spec.data` is overwritten with the actual aggregated rows after the LLM call. This is a structural guarantee, not a prompt instruction.

**Response:**

```json
{
  "visualizations": [{"type": "grouped_bar_chart", "type_category": "categorical", ...}],
  "meta": {
    "request_id": "a1b2c3d4-...",
    "stage_timings": {"query_analysis": 3100, "data_retrieval": 6200, ...},
    "api_calls": [{"endpoint": "/studies", "record_count": 175, ...}, ...],
    "total_studies_analyzed": 295
  }
}
```

A developer can take the `request_id`, grep the structured logs, and reconstruct exactly what happened at every stage.

---

## API Reference

### POST /api/v1/query

The single endpoint. Send a question, get back a visualization spec.

**Minimal request:**

```json
{ "query": "How are Pembrolizumab trials distributed across phases?" }
```

**Full request with all options:**

```json
{
  "query": "Lung cancer trials by phase",
  "input_mode": "supplement",
  "drug_name": "Pembrolizumab",
  "condition": "lung cancer",
  "sponsor": null,
  "trial_phase": "PHASE3",
  "trial_status": "RECRUITING",
  "country": "United States",
  "start_year": 2020,
  "end_year": 2025,
  "include_citations": true,
  "max_citations_per_group": 3,
  "max_studies": 5000,
  "viz_category_preference": null
}
```

**Request fields:**

| Field                     | Type   | Default        | Description                                                                |
| ------------------------- | ------ | -------------- | -------------------------------------------------------------------------- |
| `query`                   | string | _required_     | Natural language question (min 3 chars)                                    |
| `input_mode`              | string | `"supplement"` | How to combine query + params (see below)                                  |
| `drug_name`               | string | null           | Drug/intervention filter                                                   |
| `condition`               | string | null           | Disease/condition filter                                                   |
| `sponsor`                 | string | null           | Sponsor organization filter                                                |
| `trial_phase`             | string | null           | Phase filter (validated: PHASE1, PHASE2, PHASE3, PHASE4, EARLY_PHASE1, NA) |
| `trial_status`            | string | null           | Status filter (validated: RECRUITING, COMPLETED, etc.)                     |
| `country`                 | string | null           | Country filter                                                             |
| `start_year`              | int    | null           | Include trials from this year onward                                       |
| `end_year`                | int    | null           | Include trials up to this year                                             |
| `include_citations`       | bool   | false          | Include source trial references per data point                             |
| `max_citations_per_group` | int    | 5              | Cap citations per visualization group                                      |
| `max_studies`             | int    | 5000           | Safety cap on total records fetched                                        |
| `viz_category_preference` | string | null           | Hint for preferred viz category                                            |

**Input modes — how query text and structured params combine:**

| Mode                   | Query text provides  | Params provide    | Conflicts                   |
| ---------------------- | -------------------- | ----------------- | --------------------------- |
| `supplement` (default) | Intent + entities    | Confirmed filters | Params win, conflict logged |
| `override`             | Analysis intent only | All filters       | Params are source of truth  |
| `query_only`           | Everything           | Ignored           | Params logged as unused     |

**Response structure:**

```json
{
  "visualizations": [
    {
      "task_id": "task_1",
      "description": "Bar chart: single categorical dimension (phase_label) with 6 values",
      "type": "bar_chart",
      "type_category": "categorical",
      "title": "Phase Distribution of Pembrolizumab Trials",
      "encoding": {
        "category": { "field": "phase_label" },
        "value": { "field": "count" }
      },
      "data": [
        { "phase_label": "Phase 2", "count": 67 },
        { "phase_label": "Phase 3", "count": 41 },
        { "phase_label": "Phase 1", "count": 28 }
      ],
      "rendering_hints": {
        "color_scheme": "sequential_blue",
        "sort_order": "descending"
      },
      "citations": null
    }
  ],
  "meta": {
    "request_id": "a1b2c3d4-e5f6-...",
    "original_query": "How are Pembrolizumab trials distributed across phases?",
    "input_mode": "supplement",
    "input_interpretation": {
      "from_query": { "drug": "Pembrolizumab" },
      "from_params": {},
      "conflicts": [],
      "resolution": "supplement mode: no params provided"
    },
    "query_complexity": "simple",
    "filters_applied": { "query.intr": "Pembrolizumab" },
    "total_studies_analyzed": 175,
    "api_calls": [
      {
        "endpoint": "/studies",
        "params": { "query.intr": "Pembrolizumab" },
        "status_code": 200,
        "record_count": 175,
        "duration_ms": 4200
      }
    ],
    "stage_timings": {
      "query_analysis": 3100,
      "data_retrieval": 4500,
      "aggregation_task_1": 12,
      "viz_generation_task_1": 2800
    },
    "api_version": "2.0.5",
    "data_refresh": "2026-07-21T09:00:05",
    "source": "clinicaltrials.gov"
  }
}
```

**Error responses:**

```json
{"detail": {"error": "invalid_phase", "message": "...", "valid_values": ["PHASE1", ...]}}
```

### GET /health

Returns cache status and API version. Use for monitoring.

---

## Visualization Type System

The system doesn’t hardcode chart types. `type` is an open string — the LLM can recommend any visualization. `type_category` (7 values) constrains the encoding structure so a frontend knows how to render it:

| Category         | Examples                    | When used                     | Encoding                   |
| ---------------- | --------------------------- | ----------------------------- | -------------------------- |
| **categorical**  | bar, pie, treemap, lollipop | Single dimension counts       | `{category, value}`        |
| **temporal**     | line, area, gantt           | Trends over time              | `{time, value, series}`    |
| **relational**   | network, chord, sankey      | Entity relationships          | `{source, target, weight}` |
| **spatial**      | choropleth, bubble map      | Geographic data               | `{location, value}`        |
| **matrix**       | heatmap                     | Two-dimensional distributions | `{x, y, color}`            |
| **hierarchical** | sunburst, radial tree       | Multi-level breakdowns        | `{levels[], value}`        |
| **distribution** | histogram, box plot         | Value distributions           | `{value, bins}`            |

A frontend needs 7 renderers (one per category), not a renderer per chart type. `rendering_hints` provides optional styling suggestions (color scheme, orientation, scale type).

---

## What Queries Can You Ask?

The system handles diverse query patterns through a single generic pipeline:

| Query type        | Example                                        | Viz category |
| ----------------- | ---------------------------------------------- | ------------ |
| Distribution      | "Pembrolizumab trials across phases"           | categorical  |
| Time trend        | "Lung cancer trial count per year since 2015"  | temporal     |
| Comparison        | "Compare Pembrolizumab vs Nivolumab by phase"  | categorical  |
| Geographic        | "Countries with most recruiting HIV trials"    | spatial      |
| Network           | "Sponsor-drug relationships for breast cancer" | relational   |
| Hierarchical      | "Trials by sponsor type → sponsor → drug"      | hierarchical |
| Enrollment spread | "Enrollment distribution for Phase 3 trials"   | distribution |
| Heatmap           | "Sponsor types over time for diabetes"         | matrix       |

These all use the same pipeline — no query-type-specific code paths. The system was tested with 13 anti-overfit queries using drugs, conditions, and fields not in any example, and all produced valid results without code changes.

---

## Design Decisions That Matter

### 1. Two LLM calls, not a ReAct loop

Each LLM call is a hallucination surface. A ReAct agent with open-ended tool use could make 5-10 LLM calls with unpredictable results. Our pipeline uses exactly 2, with validated contracts between every stage.

### 2. Validate against the live API, not hardcoded lists

At startup, the service fetches valid enum values from ClinicalTrials.gov (`/studies/enums`). Validation runs against this live set. If the API adds a new phase or status tomorrow, our system picks it up automatically.

### 3. The aggregator is field-blind

A single `aggregate()` function handles any field, any metric, any output mode. It was deliberately tested with fields not used in any example (`study_type`, `intervention_types`) to prove generality. No `if field == "phase_label"` anywhere.

### 4. Per-stage model configuration

Stage 1 (planning) uses `gpt-4o` for strong reasoning. Stage 4 (formatting) uses `gpt-5.4-nano` — chosen via a 15-run diagnostic showing 3/3 reliability on rendering_hints vs gpt-4o-mini’s 1/9. Each stage’s model is independently configurable.

### 5. Data injection as a structural guarantee

The viz generator LLM cannot invent data. After the LLM produces a spec, `spec.data` is overwritten with the actual aggregated rows. This is enforced in code, not by prompting.

### 6. The anti-overfit gate caught a real bug

The Phase 11 gate tests ran 13 queries not in any example. Two failed — because `filter.phase` isn’t a valid ClinicalTrials.gov v2 parameter (our API reference was wrong). The fix was a one-function generic translation in the API client. Zero per-query special cases were added.

See `docs/DECISIONS.md` for the full decision log with tradeoffs.

---

## Testing

```bash
make test                                    # 100 hermetic tests (<2s)
pytest tests/test_anti_overfit.py -m integration  # 13 live anti-overfit queries
pytest tests/ -m integration                  # all integration tests
```

| Test file            | Count | What it covers                                   |
| -------------------- | ----- | ------------------------------------------------ |
| test_schemas.py      | ~15   | Model validation, round-trips, constraints       |
| test_date_parser.py  | 9     | All CT.gov date format variations                |
| test_ct_client.py    | 12    | Record normalization + live API smoke            |
| test_validators.py   | 14    | Enum validation, field checks, output_mode rules |
| test_aggregator.py   | 18    | All 3 output modes + anti-overfit field          |
| test_pipeline_e2e.py | ~10   | Full pipeline integration                        |
| test_anti_overfit.py | 13    | Unseen queries proving generality                |

The anti-overfit tests are the most important: 10 queries using drugs (Trastuzumab), conditions (Crohn’s, HIV, lymphoma), and fields (study_type) that appear nowhere in the problem statement examples. All pass without code changes.

---

## Configuration

```bash
# .env
OPENAI_API_KEY=your-key                      # Required
LLM_MODEL_QUERY_ANALYZER=gpt-4o-2024-08-06   # Stage 1: planning
LLM_MODEL_VIZ_GENERATOR=gpt-5.4-nano         # Stage 4: viz spec
LLM_MODEL_EXTRACTOR=gpt-4o-mini              # Stage 2.5: extraction (v2)
CT_API_BASE_URL=https://clinicaltrials.gov/api/v2
CT_API_PAGE_SIZE=1000                        # Always max (API default is 10)
CT_API_MAX_PAGES=10                          # Safety cap: 10K studies
CT_API_TIMEOUT_SECONDS=30
CT_API_RATE_LIMIT_DELAY=1.2                  # ~50 req/min API limit
LOG_LEVEL=INFO
```

---

## Performance

| Operation           | Latency | Bottleneck                        |
| ------------------- | ------- | --------------------------------- |
| Health check        | <1s     | —                                 |
| Simple query        | ~13-16s | LLM calls (2 × 3-4s) + CT.gov API |
| Comparison query    | ~20-25s | 2 API fetches + LLM               |
| Aggregation         | <100ms  | pandas in-memory                  |
| Cold start (Render) | ~30-60s | Container boot + cache load       |

---

## Limitations and What’s Next

**Current limitations:**

- Queries that need data from free-text fields (dosages, endpoints, eligibility criteria) aren’t supported yet — the extraction pipeline (Stage 2.5) is architected but not fully implemented
- `start_year`/`end_year` filter by post-retrieval filtering, not API-level (CT.gov v2 has no simple year param)
- No drug synonym resolution by default ("Keytruda" won’t find "Pembrolizumab" unless `normalize_entities=true` is implemented)
- Query latency is 13-16s due to two LLM calls — could be reduced with caching or a faster model

**What I’d build with more time:**

- Free-text extraction with batched LLM calls for large result sets
- Response caching for repeated query patterns
- `field_stats` retrieval strategy for broad queries matching 100K+ trials
- A demo frontend rendering the viz specs with Chart.js or D3
- Streaming response for long-running queries

---

## AI Tools and Methodology

**Design:** Claude (Anthropic) for pair-designing the architecture through conversation. Every design decision — the 4-stage pipeline, the open visualization type system, the input mode semantics, the anti-overfit testing strategy — was deliberated and documented before any code was written.

**Implementation:** Claude Code (Opus 4.8) executing a phase-by-phase build plan with mandatory checkpoints. Each phase was reviewed and approved before proceeding. The build plan, design docs, and test specs were written first, then implementation followed the specs.

**Model selection:** Diagnostic-driven. Stage 4’s model (gpt-5.4-nano) was chosen by running 15 test generations across 3 candidate models and measuring rendering_hints reliability (3/3 vs 1/9). Documented in `docs/DECISIONS.md`.

**Validation:** 100 hermetic tests (no network, no LLM) covering models, parsing, normalization, validation, and all 3 aggregation modes. 13 live anti-overfit queries proving the system handles drugs, conditions, and fields it has never seen. The anti-overfit gate caught a real API compatibility bug — and the fix was generic, not per-query.

**What was designed deliberately vs generated:**

- _Deliberate:_ Pipeline architecture, visualization type system, input modes, anti-overfit philosophy, per-stage model config, aggregation output modes, encoding contracts
- _Generated and adapted:_ Individual module implementations, test fixtures, date parsing patterns, prompt template formatting

---

## Example Runs

See `examples/` for 5 complete request-response pairs:

1. **Phase distribution** — `bar_chart` / categorical
2. **Time trend** — `line_chart` / temporal
3. **Drug comparison** — `grouped_bar_chart` / categorical
4. **Geographic** — country distribution
5. **Network** — `force_directed_network` / relational (121 edges)

---

## Branches

| Branch      | Purpose                                                                                                | Status         |
| ----------- | ------------------------------------------------------------------------------------------------------ | -------------- |
| `release-1` | **Stable submission.** Core pipeline + V2.1 deep citations + V2.2 year filtering + deployed on Render. | ✅ Stable      |
| `main`      | Active development. V2.3+ features land here first.                                                    | 🚧 Development |

`release-1` includes:

- Complete 4-stage pipeline (Phases 0-12)
- 100 hermetic tests + 13 anti-overfit integration tests (all passing)
- Deep citations (V2.1) — per-data-point source trial references
- Year filtering (V2.2) — post-retrieval filtering with metadata notes
- Dockerized, deployed on Render with auto-deploy
- Full decision log in docs/DECISIONS.md

### Future Enhancements (post release-1)

These are architected and have implementation guides in `docs/impl/` but are not in the stable release:

**V2.3 — field_stats retrieval strategy:** Use ClinicalTrials.gov's `/stats/field/values` endpoint for broad, unscoped distribution queries (e.g., "how are ALL trials distributed across phases?"). Returns exact counts over 478K+ trials in a single API call vs study_search's 5,000-trial sample. API verification confirmed the endpoint is global-only (rejects scoping params), so this is restricted to unfiltered queries.

**V2.4 — Entity normalization:** Optional LLM call between Stage 1 and Stage 2 that resolves drug brand names to generic names (Keytruda → Pembrolizumab) and common condition names to MeSH terms. Gated behind a `normalize_entities` request parameter. Uses the extractor model (gpt-4o-mini).

**V2.5 — Free-text extraction (Stage 2.5):** Extract structured data from study descriptions when the query requires a field not on StudyRecord (e.g., dosage, endpoints). Individual extraction mode for ≤20 records, with honest sampling notes for larger sets. Merges extracted fields into the aggregation path via pandas DataFrame join.
