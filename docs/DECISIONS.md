# Decisions

Log format per phase: **Chose / Over / Because / Tradeoff.**

---

## Phase 0 — Environment Setup

**2026-07-21 — LLM provider & models**
- **Chose:** OpenAI, with two independently configurable models: `LLM_MODEL_MAIN` (default `gpt-4o`) for Stage 1 query analysis (the planner), and `LLM_MODEL_SUBAGENT` (default `gpt-4o-mini`) for Stage 4 viz generation and other secondary LLM calls (e.g. Stage 2.5 extraction, v2). Both are env vars, never hardcoded in pipeline code.
- **Over:** Anthropic Claude; and over a single shared model for both stages.
- **Because:** No Anthropic API key is available — the project standardizes on OpenAI (user direction, 2026-07-21). Splitting main vs subagent models lets the heavy planning call (Stage 1) use a stronger model while cheaper formatting calls (Stage 4) use a smaller one, tunable per deployment. OpenAI structured outputs (`response_format` json_schema + `strict`) provide the anti-hallucination guarantee the DESIGN requires. Model IDs stay in config, satisfying the no-overfitting rule.
- **Tradeoff:** Two models to tune instead of one. Defaults are placeholders the operator overrides in `.env` (or via real env vars) — no code change needed to switch models.

> **Correction (2026-07-21):** An earlier draft of this decision chose Anthropic `claude-opus-4-8`. Reverted to OpenAI per user direction (no Anthropic key). `requirements.txt` now depends on `openai`, not `anthropic`; config exposes two OpenAI model fields.

**2026-07-21 — HTTP client**
- **Chose:** `httpx` (async).
- **Over:** `requests` (sync), `aiohttp`.
- **Because:** DESIGN specifies async retrieval with pagination/retry; FastAPI is async-native; httpx's built-in `MockTransport` lets us test `ct_client` without a mocking dependency.
- **Tradeoff:** None material.

**2026-07-21 — API access verified**
- `GET /api/v2/version` → apiVersion `2.0.5`, dataTimestamp `2026-07-21T09:00:05`.
- Smoke query `query.intr=Pembrolizumab&countTotal=true` → `totalCount: 2906`. No API key required, as documented.

---

## Phase 1 — Schemas

**2026-07-21 — Single source of truth for the 7 viz categories**
- **Chose:** Define `VizCategory` once in `intent.py` and import it into `response.py` for `VisualizationSpec.type_category`.
- **Over:** Repeating the 7-value `Literal` in both `AnalysisTask.candidate_viz_categories` and `VisualizationSpec.type_category`.
- **Because:** The category set is a hard contract; duplicating the literal invites drift where the two lists diverge.
- **Tradeoff:** `response.py` now depends on `intent.py` (already depends on `trial_record.py` for `APICallRecord`). One-directional, no cycle.

**2026-07-21 — `type` open string, `type_category` constrained**
- **Chose:** `VisualizationSpec.type` is a free `str`; `type_category` is the 7-value `Literal`.
- **Because:** Per DESIGN, the frontend needs one renderer per *category* (7), and `type` only names the variant. Keeping `type` open means new chart names never require a schema change (anti-overfit) while `type_category` still guarantees a valid encoding contract.

**2026-07-21 — PipelineContext dedup keying**
- **Chose:** `add_studies` keys the studies dict by bare `nct_id`, or `"{entity_tag}:{nct_id}"` when a tag is given.
- **Over:** Keying purely by `nct_id`.
- **Because:** A study matching both arms of a comparison ("Drug A vs Drug B") must count in both arms; a pure-nct_id key would silently drop it from the second arm.
- **Tradeoff:** The same study can appear twice in `get_all_studies()` across arms — correct for comparative aggregation, noted as a `ponytail:` upgrade point if arms ever need independent per-study metadata.

**2026-07-21 — Test import path**
- **Chose:** `app/__init__.py` (make `app` a real package) + empty root `conftest.py` (puts repo root on `sys.path`).
- **Because:** pytest's default import mode inserts the test file's dir, not the repo root, so `import app` needs help; a root `conftest.py` is the standard, dependency-free fix.

**Checkpoint (from PLANNING.md):**
- [x] All models importable and round-trip (dump → validate) — `test_10`.
- [x] QueryRequest rejects invalid input_mode, short queries — `test_1`, `test_2`.
- [x] VisualizationSpec.type is open string, type_category is Literal — `test_7`, `test_8`.

---

## Phase 2 — Utilities

**2026-07-21 — Date parsing: tolerant regex, never raises**
- **Chose:** Two anchored regexes (numeric ISO/year-month/year, and month-word+year) plus a month-name lookup (full + 3-letter). Unrecognized input returns `(None, None)`.
- **Over:** `dateutil.parser` / chained `strptime` attempts.
- **Because:** CT.gov dates are irregular and frequently partial ("January 2024", bare "2024"); a partial-tolerant parser that yields `(year, month)` fits the StudyRecord shape and avoids a dependency. Numeric months out of 1–12 are dropped, not guessed.
- **Tradeoff:** Won't parse locales/formats outside the documented CT.gov set (e.g. non-English month names) — acceptable; CT.gov is English-only.

**2026-07-21 — `safe_get` lives in `app/utils/helpers.py`**
- **Chose:** A dedicated `helpers.py` rather than colocating `safe_get` in `date_parser.py`.
- **Because:** `safe_get` is a generic nested-dict navigator the Phase 3 normalizer leans on heavily; it doesn't belong in a date module. One small file with a clear name beats semantic pollution.
- **Tradeoff:** One extra file — justified by cohesion.

**2026-07-21 — Config: OpenAI key optional at load, module singleton**
- **Chose:** `openai_api_key: str | None = None`; `settings = Settings()` exported as a singleton; `extra="ignore"` so unrelated env vars don't break load.
- **Because:** Phases 2–6 are LLM-free and must load without credentials; the query analyzer (Phase 7) fails loudly if the key is still missing. A singleton avoids re-reading `.env` on every import.
- **Tradeoff:** A missing key is caught at Stage 1, not at startup — acceptable and matches the phased build.

**2026-07-21 — Logger `propagate = False`**
- **Chose:** Disable propagation on loggers created by `get_logger`.
- **Because:** Prevents duplicate lines when a root handler is also configured (common under pytest / uvicorn).

**Checkpoint (from PLANNING.md):**
- [x] All 9 date parsing scenarios pass — `test_parse_date_cases` (+7 extra edge cases).
- [x] Logger outputs structured JSON with request_id — `test_logger_emits_json_with_request_id`.
- [x] Config loads from `.env` — `test_config_loads_defaults`.

---

## Phase 3 — API Client

**2026-07-21 — Verified real field paths before writing the normalizer**
- Fetched a live study (`NCT03769532`) and the `/stats/field/values` response, confirming every path in the impl mapping (`leadSponsor.name`/`.class`, `designModule.phases`, `startDateStruct`/`completionDateStruct` = `{date,type}`, `enrollmentInfo.count`, `locations[].country/city`, `stats` blocks with `topValues[{value, studiesCount}]`).
- **Because:** a parser written against guessed paths silently produces empty records. Confirm the data shape first.

**2026-07-21 — `phase_label` is a general formatter, not enum routing**
- **Chose:** Strip the `PHASE`/`EARLY_PHASE` prefix and format generically (`PHASE3` → "Phase 3"), with `NA` → "N/A".
- **Because:** This is display formatting that generalizes to any phase token — not value-specific branching that changes behavior. It does not violate the no-overfit rule (which targets `if drug == "..."` / chart-type routing).

**2026-07-21 — Client is per-request; search/filter params pass through**
- **Chose:** `CTGovClient` instantiated per request, accumulating `APICallRecord`s in `self.api_calls`; `search_params`/`filter_params` from the `DataRequirement` are merged into the query string verbatim.
- **Over:** A shared singleton client with cross-request call logs; hardcoding a semantic→CT.gov field mapping inside the client.
- **Because:** Per-request isolation matches the "no cross-request state" design. Pass-through params keep the client generic — the LLM/validator produces valid CT.gov keys, so the client never needs drug/field-specific logic (anti-overfit).
- **Tradeoff:** Added an optional `request_id` param to `__init__` (not in the impl signature) purely for log correlation.

**2026-07-21 — Retry, rate limit, truncation**
- Exponential backoff (`2**attempt`, max 3 retries) on 429/5xx and transport errors; other 4xx raise immediately. `1.2s` sleep between pages (~50 req/min). Truncation flagged whenever `totalCount > len(returned)` (covers both the `max_studies` cap and the `max_pages` ceiling).

**2026-07-21 — Integration test isolation**
- **Chose:** `pyproject.toml` sets `asyncio_mode = "auto"`, registers an `integration` marker, and `addopts = -m 'not integration'` so the default `pytest tests/` stays hermetic and offline; the live smoke runs via `pytest -m integration`.
- **Because:** Future phases run `pytest tests/` every time; baking a live network call into that would make due diligence flaky when offline.

**Checkpoint (from PLANNING.md):**
- [x] `normalize_study` handles complete, minimal, multi-phase, null records — `test_2_1`..`test_2_10`.
- [x] `phase_label` correctly generated — `test_phase_label_all_scenarios`.
- [x] Live API smoke test passes — `test_2_11` (run with `-m integration`).
- [x] API calls logged with structured JSON — `_log_call` emits `api_call` events + populates `self.api_calls`.

---

## Phase 4 — Reference Cache

**2026-07-21 — Verified enum/metadata shapes before parsing**
- `/studies/enums` is a **list** of `{type, values:[{value,legacyValue}], pieces}` — keyed by `type`, so `valid_phases = enums["Phase"]`, `valid_statuses = enums["Status"]`, `valid_sponsor_classes = enums["AgencyClass"]`. `/studies/metadata` is a list of 6 module trees. `/version` gives `apiVersion` + `dataTimestamp`.

**2026-07-21 — Per-source independent fallback**
- **Chose:** Guard each of the three fetches separately; a failure logs a WARNING and leaves that piece on its static fallback while the others still load. `load()` never raises.
- **Because:** A flaky metadata endpoint shouldn't cost us the enums (which validation depends on). Startup must always succeed.

**2026-07-21 — FALLBACK_* constants: a sanctioned exception to the no-hardcoded-enums rule**
- The impl guide explicitly mandates static `FALLBACK_PHASES/STATUSES/SPONSOR_CLASSES` for startup resilience only. Pipeline code reads `cache.valid_*`, never the constants — verified: a grep shows `FALLBACK_` is referenced solely inside `reference_cache.py`. Live load proves the cache tracks the API, not the fallback (live returned **14** statuses / **9** sponsor classes vs the 8/4-value fallbacks). This is not overfitting: no pipeline branch routes on a specific enum value.

**2026-07-21 — Added a hermetic fallback test (plan said manual-only)**
- **Chose:** A small `tests/test_reference_cache.py` with a hermetic fallback test (`localhost:1` → immediate ConnectError → fallback preserved) plus a live-load integration test.
- **Over:** Manual-only verification per the impl guide.
- **Because:** The fallback is a real branch; ponytail requires one runnable check for non-trivial logic. The live part stays manual/integration-gated.

**Checkpoint (from PLANNING.md):**
- [x] Cache loads from live API — manual verify: api_version `2.0.5`, 41 enum types, 6 metadata modules.
- [x] `valid_phases` / `valid_statuses` populated — live: 6 phases (incl. PHASE3), 14 statuses (incl. RECRUITING).
- [x] Graceful fallback when API unreachable — `test_graceful_fallback_when_api_unreachable`.

---

## Phase 5 — Validators

**2026-07-21 — Two validation gates, different failure types**
- **Chose:** `validate_structured_hints` (pre-LLM) raises `fastapi.HTTPException(400)` with the valid enum list; `validate_intent` (post-Stage-1, pre-Stage-2) raises a custom `IntentValidationError`.
- **Because:** A bad request hint is a client 400 we want to catch *before* spending an LLM call. An invalid intent is an interpretation failure the orchestrator maps into a structured `ErrorResponse`. Different origins → different exception types the caller handles distinctly.

**2026-07-21 — Valid values come from the cache; filter keys map structurally**
- **Chose:** All enum checks read `cache.valid_phases` / `.valid_statuses` / `.groupable_fields`. `_FILTER_ENUM_ATTR` maps CT.gov filter param names (`filter.phase`, `filter.overallStatus`) to the cache attribute holding their valid values; pipe-delimited values are split and each token checked.
- **Because:** Keeps validation tracking the live enum set (no hardcoded value lists), while the param→enum mapping is structural CT.gov knowledge, not data overfitting.

**2026-07-21 — Check ordering & output_mode consistency**
- Counts first (tasks ≤ 4, requirements ≤ 5), then filter-enum values, then per-task group_by / metric_field / categories / output_mode. Consistency rules: `raw_records` ⇒ `distribution` in candidates; `edge_list` ⇒ `relational` in candidates **and** exactly 2 group_by fields. `metric_field` required (and must be a real field) for `sum`/`collect`/`unique_count`.

**Checkpoint (from PLANNING.md):**
- [x] Invalid enums rejected with valid values listed — `test_3_2`, `test_3_8`.
- [x] Invalid group_by fields rejected — `test_3_3`.
- [x] output_mode consistency enforced — `test_3_6`, `test_3_7`.
- [x] Task / requirement count limits enforced — `test_3_4`, `test_3_5`.

---

## Phase 6 — Aggregator (the anti-overfit core)

**2026-07-21 — Fully generic; branch only on metric / output_mode**
- **Chose:** One `aggregate()` dispatching on `spec.output_mode`; grouping/pivoting driven entirely by `spec.group_by` / `spec.metric_field`. The only fixed field references anywhere are `nct_id` and `excerpt`.
- **Because:** The no-overfit rule forbids branching on group-by field names (`phase_label`, `sponsor_name`, …) — verified none appear. `nct_id`/`excerpt` are the **deep-citations contract** from the problem statement (each cited datum → `nct_id` + `excerpt`), so they are structural identifiers, not routing. Proven by `test_4_16` (`group_by=["study_type"]`, a field used nowhere else, works unchanged).

**2026-07-21 — Row-loop over groups instead of vectorized key-matching**
- **Chose:** Iterate `df.groupby(by, dropna=False)` in Python, computing metric + citations per group in one pass.
- **Over:** Pure-pandas aggregation then re-joining citations by group key.
- **Because:** Attaching citations by group key is painful when keys are NaN (`NaN != NaN`); a per-group loop sidesteps it and reads clearly. Group count is small (distinct values), so this is not a hot path.

**2026-07-21 — numpy→native coercion**
- `_native` converts numpy scalars via `.item()` and collapses whole floats (a NaN-containing int column becomes float, so `2015.0 → 2015`), keeping output JSON-clean and stable. `_missing` treats `None`/`NaN` as the `"Unknown"` group.

**2026-07-21 — Sorting**
- Explicit `sort_by` ∈ {value_desc, value_asc, key_desc, key_asc}. Default: `key_asc` when `time_granularity` is set (chronological), else `value_desc` (most common first). `"Unknown"`/missing keys sort last; `collect` (list values) falls back to key sort.

**Known ceilings (`ponytail:` upgrade points):**
- `sum` assumes a numeric `metric_field` (validator guarantees it exists, not that it's numeric).
- `edge_list` counts all source×target pairs; self-pairs and within-record duplicates aren't deduped — fine for sponsor×drug, a v2 concern for drug×drug networks.

**Checkpoint (from PLANNING.md):**
- [x] All 3 output modes work — `test_4_1`..`test_4_15`.
- [x] List field explosion works — `test_4_3`, `test_4_14`.
- [x] Empty input returns empty — `test_4_9`.
- [x] Works with a field NOT in the examples (anti-overfit) — `test_4_16` (`study_type`).

---

## Phase 7 — Query Analyzer (Stage 1 LLM)

**2026-07-21 — OpenAI provider re-confirmed & key verified**
- Live check: key authenticates (12 models); a 1-token call on `gpt-4o` (→ `gpt-4o-2024-08-06`) and `gpt-4o-mini` both succeed. Both support structured/JSON output. No replacement needed.

**2026-07-21 — OpenAI SDK directly, JSON mode + validate + retry (not LangChain, not strict structured outputs)**
- **Chose:** `AsyncOpenAI` with `response_format={"type":"json_object"}`, then `QueryIntent.model_validate(json.loads(...))`, retrying once with the error message on failure.
- **Over:** LangChain (impl suggestion); OpenAI strict structured outputs.
- **Because:** We standardized on the `openai` SDK — no need for LangChain. Strict json_schema can't represent `DataRequirement.search_params`/`filter_params` (free-form `dict` → `additionalProperties:true`), so JSON mode + Pydantic validation is the robust path and matches the impl's own steps (parse → validate → retry). `original_query` is set to the real query post-validation.

**2026-07-21 — Fixed 3 builder bugs in the pre-populated prompt (SYSTEM_PROMPT text untouched)**
- `build_query_analyzer_prompt` used `str.format`, but the template uses `{{double-brace}}` placeholders (which `format` treats as literals) and the injected JSON schema is full of braces → switched to targeted `str.replace`.
- Enum keys were `"OverallStatus"`/`"LeadSponsorClass"` → the live CT.gov enum keys are `"Status"`/`"AgencyClass"` (Phase 4). Left as-was they'd inject empty lists.
- `build_mode_instruction` was defined twice (identical) → deduped.
- The user's authored prompt content was preserved verbatim; only the plumbing was corrected. Prompt version bumped to `2026-07-21-b` in a comment.

**2026-07-21 — Two-layer output_mode requirements (fixes the Q4 network false-reject)**
- **Problem:** the validator required `metric_field` for `metric=collect` unconditionally, rejecting a *correct* `edge_list` network plan — but the aggregator's `_edge_list` ignores `metric`/`metric_field` entirely.
- **Layer 1 (validator):** `_OUTPUT_MODE_REQUIREMENTS` encodes what each mode truly needs — `aggregated` needs a field only for `sum`/`unique_count`; `raw_records` always needs the value field; `edge_list` needs exactly 2 group_by fields and no metric.
- **Layer 2 (aggregator):** each mode function starts with a runtime guard raising `AggregationError` if it genuinely can't run (edge_list ≠ 2 fields, raw_records w/o field, aggregated sum/unique_count w/o field); an ignored `metric_field` on edge_list is logged at DEBUG and skipped.
- **Result:** hallucinated intents fail loudly at one of the two layers; valid plans (Q4) pass. `collect` without a field degrades to `[]` (not a crash), so it isn't required.

**2026-07-21 — Q3 (vague override query) note**
- "show me" + `drug_name` in override mode: override works (the retrieval filter is sourced from the param, not query text). The contentless query led the LLM to a degenerate `raw_records`-by-`nct_id` plan with no value field, which Layer 1 correctly rejects — the guardrail working as intended, not a bug. The demonstration test asserts the override sourcing, not plan validity.

**Manual verification (live, gpt-4o):**
- Q1 "distribution across phases" → simple, 1 req, categorical `group_by=[phase_label]` — valid.
- Q2 "Pembro vs Nivolumab" → **comparative, 2 reqs entity-tagged**, `group_by=[phase_label, entity_tag]` — valid.
- Q3 override → plan sourced from `drug_name` param (override works).
- Q4 "network of sponsors and drugs" → relational `edge_list`, `group_by=[sponsor_name, interventions]` — valid (post-fix).

**Checkpoint (from PLANNING.md):**
- [x] Simple query produces valid QueryIntent — Q1.
- [x] Comparison query produces 2 data requirements with entity_tags — Q2.
- [x] Override mode changes behavior — Q3.
- [x] LLM call logged with model, tokens, duration — `llm_call` event (model `gpt-4o-2024-08-06`, prompt/completion tokens, duration_ms).

---

## Phase 8 — Viz Generator (Stage 4 LLM)

**2026-07-21 — Per-stage model configuration**
- **Chose:** One model per LLM stage instead of a shared main/subagent pair: `llm_model_query_analyzer` (default `gpt-4o`, Stage 1 planning), `llm_model_viz_generator` (Stage 4 viz spec), `llm_model_extractor` (default `gpt-4o-mini`, Stage 2.5 extraction, v2). Env vars `LLM_MODEL_QUERY_ANALYZER` / `LLM_MODEL_VIZ_GENERATOR` / `LLM_MODEL_EXTRACTOR`.
- **Over:** The earlier two-field `LLM_MODEL_MAIN` / `LLM_MODEL_SUBAGENT` split.
- **Because:** Each stage has different needs (planning wants reasoning; viz-spec is formatting; extraction is bulk). Naming by stage makes the config self-documenting and lets each be tuned independently. Supersedes the Phase 0 two-model naming.

**2026-07-21 — Stage 4 model choice (rendering_hints diagnostic)**
- **Chose:** `gpt-5.4-nano` for `llm_model_viz_generator`, **over** `gpt-4o-mini`, because the diagnostic showed `rendering_hints` present **3/3 vs 1/9** (relational/matrix/distribution). Both models pick the correct chart type every time; only gpt-4o-mini omits the optional hints (a model limitation, not a prompt gap). `gpt-4.1-mini` was also 3/3 but nano is the smaller tier with the richest hints.
- **Plus a defensive fallback (fix B):** `generate()` injects a per-category `color_scheme` when `rendering_hints` comes back empty — belt-and-suspenders so the frontend always has a scheme if a future model regresses.
- **Data injection stands regardless of model:** `generate()` overwrites `spec.data` with the real aggregated rows, so the model never supplies data — "never invent data" is structural, not prompt-dependent.

**Checkpoint (from PLANNING.md):**
- [x] Produces valid VisualizationSpec — 5-shape live verification.
- [x] encoding matches type_category contract — `_verify_encoding` (+ retry on mismatch).
- [x] description justifies type choice — prompt-enforced; validated non-empty.
- [x] title is specific, rendering_hints present — model emits hints (gpt-5.4-nano) with a code fallback guaranteeing presence.

---

## Phase 9 — Orchestrator + Data Retriever

**2026-07-21 — Query-analyzer model: pinned dated snapshot**
- **Chose:** `gpt-4o-2024-08-06` (config default, `.env`, `.env.example`) for `llm_model_query_analyzer`.
- **Because:** This project's OpenAI key has access to the dated snapshot but **not** the bare `gpt-4o` alias (403 `model_not_found`). A Phase-8 config "normalization" had rewritten the pin to `gpt-4o` and broke Stage 1; restored to the accessible snapshot. A deployment whose key has alias access can switch back to `gpt-4o`.

**2026-07-21 — execute(): per-request pipeline with request_id + timings**
- Generates a UUID4 `request_id`, stamps it on the (per-request) `CTGovClient` for log correlation, threads a fresh `PipelineContext`, and wraps each stage in `timed_stage`. `task_data_map` + entity-tag selection means data is fetched once per requirement and shared across tasks (no redundant API calls).

**2026-07-21 — merge_and_validate: three input modes**
- `query_only`: params ignored, recorded in `ignored_params`.
- `override`: structured hints are the sole search/filter source; a comparison collapses to a single entity (with a warning) and `entity_tag` is stripped from group_by.
- `supplement`: query is primary; params confirm/add and win conflicts (logged). An intervention hint applies **only to the matching comparison arm** (by `entity_tag`), so "Drug A vs Drug B" isn't flattened.

**2026-07-21 — Errors -> structured ErrorResponse**
- `build_error_response` maps every pipeline exception (HTTPException, IntentValidationError, QueryAnalysisError, AggregationError, VizGenerationError, generic) to an `ErrorResponse` with code/message/suggestion + request_id. Used here and by the Phase 10 endpoint.

**Known ceilings (`ponytail:` deferrals):**
- `start_year`/`end_year` hints are recorded in the interpretation but not yet applied as a hard CT.gov filter (no simple year param in the documented v2 set) — v2 refinement.
- `field_stats` / `study_detail` strategies are routed best-effort (field/nct_id pulled from `search_params`); the record-level `study_search` path is the fully-exercised one.

**Checkpoint (from PLANNING.md):**
- [x] Full pipeline: query in → PipelineResponse out — `test_e2e_simple_query`.
- [x] request_id in response and all logs — `meta.request_id` + `pipeline_start/complete` events.
- [x] stage_timings populated — 4 stages timed (query_analysis, data_retrieval, aggregation_*, viz_generation_*).
- [x] input_interpretation populated — supplement/override/query_only, `test_*` merge cases.
- [x] Errors produce structured ErrorResponse — `build_error_response` + hermetic tests.

---

## Phase 10 — FastAPI Endpoint + Examples

**2026-07-21 — App shape**
- `lifespan` loads the reference cache once at startup; `GET /health` reports cache state; `POST /api/v1/query` runs the pipeline. A **fresh CTGovClient per request** (its `api_calls` feed the response metadata — no cross-request state). Pipeline exceptions map to structured `ErrorResponse` bodies with the right status (400 hint-validation, 422 intent, 500 pipeline).

**2026-07-21 — Three robustness fixes surfaced by example generation**
- **Param whitelist (`data_retriever._strip_unsupported_params`):** the LLM invented a `start_year` API param for a "since 2015" query (→ 400). Now search/filter params are restricted to the closed CT.gov set; anything else is stripped, warned, and noted in metadata. The year dimension is handled by the temporal aggregation, not an API filter.
- **Encoding-key normalization (`viz_generator._normalize_encoding`):** the small viz model sometimes named an encoding key off-contract (spatial `country` instead of `location`). A bounded synonym map (7 contracts) renames to the contract key before verification, so the frontend always gets contract keys.
- **`field_stats → study_search` fallback:** `field_stats` is a v2 strategy not wired into the StudyRecord aggregator; when the LLM selects it, the retriever logs a warning, notes "Used study_search (capped sample) instead of field_stats (v2)", and runs the record-level path. `field_stats` stays in the Stage 1 prompt (the LLM can still recommend the ideal strategy; the retriever handles the gap) — more future-proof than hiding the capability.

**2026-07-21 — 5 examples cover the viz breadth**
- categorical (bar), temporal (line), comparison (grouped bar, 2 entity-tagged reqs), spatial (choropleth), relational (network, 428 edges). Generated by running the real pipeline; saved to `examples/`.

**Checkpoint (from PLANNING.md):**
- [x] Server starts, health check works — `test_health`.
- [x] POST returns valid response — `test_8_*`.
- [x] All e2e tests pass — 12 integration tests (8.x metadata, 9.x logging, 10.x viz contract).
- [x] 5 example JSONs in `examples/`.

---

## Phase 11 — Anti-Overfit Gate

**2026-07-21 — The gate caught a real generality bug (and validated the approach)**
- Ran 10 queries not in the examples (6.1-6.10, all 7 viz categories, unseen drugs/conditions/fields) + error cases (7.1-7.3). 2 failed — **not** from overfitting, but a wrong API param: `filter.phase` returned 400.
- **Fix (the right kind):** `filter.phase` is not a valid CT.gov v2 param — verified live (`filter.phase=PHASE3` → 400; `filter.advanced=AREA[Phase]PHASE3` → 200 with real Phase-3 data; multi-phase `AREA[Phase](PHASE1 OR PHASE2)` filters correctly). Added `ct_client._translate_phase_filter` to convert `filter.phase` → `filter.advanced` at the HTTP boundary. `filter.phase` stays the internal semantic key (validated against live enums); this is a generic adapter correction, **not** a per-query special-case — exactly what the gate is meant to force. `filter.overallStatus` was verified to work as-is.
- Corrected `docs/API_REFERENCE.md` (the Notion source wrongly listed `filter.phase` as a param).

**Result:** all 13 anti-overfit tests pass. No query required a per-query code branch; the one fix was a shared API-adapter translation that benefits every phase-filtered query.

**Checkpoint (from PLANNING.md):**
- [x] 10 non-example queries produce valid responses — `test_anti_overfit_query_produces_viz` (6.1-6.8, 6.10) + `test_6_9_vague_override_is_handled`.
- [x] No overfitting — the only code change was a generic `filter.phase`→`filter.advanced` API translation, not query-specific logic.
- [x] Error handling — `test_7_1`/`7_2`/`7_3` (zero results, short query 422, invalid enum 400).

---

## Phase 12 — Polish

**2026-07-21 — Makefile + lint**
- `Makefile`: `make test` (hermetic), `make test-integration` (live), `make lint` (ruff), `make run` (uvicorn). `ruff` added as a dev tool; `ruff check app tests` passes clean with defaults (no custom config needed).
- Reviewed `docs/DECISIONS.md`: all phases 0–11 logged. README left as-is (final version supplied by the user).
- `make test` → 100 hermetic tests pass.
