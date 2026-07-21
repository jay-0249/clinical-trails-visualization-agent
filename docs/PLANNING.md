> Read `docs/impl/phase_N_*.md` for implementation details at each phase. This file is the roadmap only.

## Reading Order (Phase 0)

1. `CLAUDE.md` — rules (~30 lines)
2. `docs/PROBLEM_STATEMENT.md` — the assignment
3. `docs/DESIGN.md` — architecture (~200 lines)
4. `docs/API_REFERENCE.md` — API endpoints and response structure
5. This file — execution rail
6. `tests/test_cases.md` — test scenarios

Read `docs/PROMPTS.md` at Phase 7-8. Read `docs/impl/phase_N_*.md` only at the current phase.

---

## Due Diligence Protocol (after EVERY phase)

1. Run `pytest tests/ -v` — all tests from current and previous phases must pass
2. Verify `docs/DECISIONS.md` has entries for this phase
3. Anti-overfit check: no hardcoded drug names, conditions, query phrases, or enum values
4. Report: what was built, what passes/fails, any concerns
5. **ASK PERMISSION before proceeding to next phase**

---

## Phase 0: Environment Setup

- Create venv, install deps, copy `.env.example` to `.env` with API key
- Verify: `curl https://clinicaltrials.gov/api/v2/version`
- Log first decision in `docs/DECISIONS.md` (LLM provider/model choice)
- **Report back before Phase 1**

---

## Phase 1: Schemas

**Read:** `docs/impl/phase_1_schemas.md`

**Create:** `app/schemas/request.py`, `response.py`, `intent.py`, `trial_record.py`

**Test:** `tests/test_schemas.py`

Checkpoint:

- [ ] All models importable and round-trip (dump → validate)
- [ ] QueryRequest rejects invalid input_mode, short queries
- [ ] VisualizationSpec.type is open string, type_category is Literal

---

## Phase 2: Utilities

**Read:** `docs/impl/phase_2_utilities.md`

**Create:** `app/utils/date_parser.py`, `app/utils/logger.py`, `app/config.py`

**Test:** `tests/test_date_parser.py` (cases 1.1-1.9)

Checkpoint:

- [ ] All 9 date parsing scenarios pass
- [ ] Logger outputs structured JSON with request_id
- [ ] Config loads from `.env`

---

## Phase 3: API Client

**Read:** `docs/impl/phase_3_api_client.md`

**Create:** `app/services/ct_client.py`

**Test:** `tests/test_ct_client.py` (cases 2.1-2.10 + integration smoke test)

Checkpoint:

- [ ] `normalize_study` handles complete, minimal, multi-phase, null records
- [ ] phase_label correctly generated
- [ ] Live API smoke test passes
- [ ] API calls logged with structured JSON

---

## Phase 4: Reference Cache

**Read:** `docs/impl/phase_4_reference_cache.md`

**Create:** `app/services/reference_cache.py`

**Test:** Manual verification

Checkpoint:

- [ ] Cache loads from live API
- [ ] valid_phases, valid_statuses populated
- [ ] Graceful fallback when API unreachable

---

## Phase 5: Validators

**Read:** `docs/impl/phase_5_validators.md`

**Update:** `app/utils/validators.py`

**Test:** `tests/test_validators.py` (cases 3.1-3.8)

Checkpoint:

- [ ] Invalid enums rejected with valid values listed
- [ ] Invalid group_by fields rejected
- [ ] output_mode consistency enforced
- [ ] Task/requirement count limits enforced

---

## Phase 6: Aggregator

**Read:** `docs/impl/phase_6_aggregator.md`

**Create:** `app/pipeline/aggregator.py`

**Test:** `tests/test_aggregator.py` (cases 4.1-4.15) — MOST IMPORTANT TEST FILE

Checkpoint:

- [ ] All 3 output modes work (aggregated, raw_records, edge_list)
- [ ] List field explosion works
- [ ] Empty input returns empty output
- [ ] Works with a field NOT in the examples (anti-overfit)

---

## Phase 7: Query Analyzer (Stage 1 LLM)

**Read:** `docs/impl/phase_7_query_analyzer.md` AND `docs/PROMPTS.md` (Stage 1 section)

**Create:** `app/prompts/query_analyzer.py`, `app/pipeline/query_analyzer.py`

**Test:** Manual — test with 4 diverse queries

Checkpoint:

- [ ] Simple query produces valid QueryIntent
- [ ] Comparison query produces 2 data requirements with entity_tags
- [ ] Override mode changes behavior
- [ ] LLM call logged with model, tokens, duration

---

## Phase 8: Viz Generator (Stage 4 LLM)

**Read:** `docs/impl/phase_8_viz_generator.md` AND `docs/PROMPTS.md` (Stage 4 section)

**Create:** `app/prompts/viz_generator.py`, `app/pipeline/viz_generator.py`

**Test:** Manual — feed different data shapes

Checkpoint:

- [ ] Produces valid VisualizationSpec
- [ ] encoding matches type_category contract
- [ ] description justifies type choice
- [ ] title is specific, rendering_hints present

---

## Phase 9: Orchestrator

**Read:** `docs/impl/phase_9_orchestrator.md`

**Create:** `app/pipeline/orchestrator.py`, `app/pipeline/data_retriever.py`

**Test:** Manual end-to-end

Checkpoint:

- [ ] Full pipeline: query in → PipelineResponse out
- [ ] request_id in response and all logs
- [ ] stage_timings populated
- [ ] input_interpretation populated
- [ ] Errors produce structured ErrorResponse

---

## Phase 10: FastAPI Endpoint + Examples

**Read:** `docs/impl/phase_10_endpoint.md`

**Create:** `app/main.py`, 5 example JSON files, `README.md`

**Test:** `tests/test_pipeline_e2e.py` (cases 8.1-8.8, 9.1-9.5)

Checkpoint:

- [ ] Server starts, health check works
- [ ] POST returns valid response
- [ ] All e2e tests pass
- [ ] 5 example JSONs in `examples/`

---

## Phase 11: Anti-Overfit Gate

**Test:** `tests/test_anti_overfit.py` (cases 6.1-6.10)

If ANY query requires a code change, the system is overfit — stop and fix.

---

## Phase 12: Polish

Finalize README, review docs/DECISIONS.md, `make test` passes clean.

---

## Phase 13 (if time): V2

Priority: deep citations → free-text extraction → field_stats strategy → demo UI

---

## Execution Summary

| Phase | Creates                       | Test file         | Depends on |
| ----- | ----------------------------- | ----------------- | ---------- |
| 0     | env                           | —                 | —          |
| 1     | schemas                       | test_schemas      | —          |
| 2     | utils + config                | test_date_parser  | 1          |
| 3     | ct_client                     | test_ct_client    | 1, 2       |
| 4     | reference_cache               | manual            | 3          |
| 5     | validators                    | test_validators   | 1, 4       |
| 6     | aggregator                    | test_aggregator   | 1          |
| 7     | query_analyzer + prompt       | manual            | 1, 2, 4    |
| 8     | viz_generator + prompt        | manual            | 1          |
| 9     | orchestrator + data_retriever | manual            | 3-8        |
| 10    | main.py • examples            | test_e2e          | 9          |
| 11    | —                             | test_anti_overfit | 10         |
| 12    | README polish                 | —                 | 10         |
