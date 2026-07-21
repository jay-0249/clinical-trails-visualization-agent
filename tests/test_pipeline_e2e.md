test_pipeline_e2e (Phase 10)

Use FastAPI TestClient. These are integration tests against the running pipeline.

## End-to-End Queries

| #   | Input                                                                  | Verify                                 |
| --- | ---------------------------------------------------------------------- | -------------------------------------- |
| 8.1 | `{"query": "How are Pembrolizumab trials distributed across phases?"}` | 1 viz, categorical, phase counts       |
| 8.2 | `{"query": "Trials for lung cancer per year since 2015"}`              | 1 viz, temporal, year-count pairs      |
| 8.3 | `{"query": "Compare Pembrolizumab vs Nivolumab by phase"}`             | 2 data reqs with entity_tags           |
| 8.4 | `{"query": "Sponsor-drug network for breast cancer"}`                  | relational, source/target/weight       |
| 8.5 | `{"query": "Countries with most recruiting diabetes trials"}`          | country + count data                   |
| 8.6 | `{"query": "...", "include_citations": true}`                          | citations array per group              |
| 8.7 | `{"query": "trials by phase", "drug_name": "Pembrolizumab"}`           | filters_applied + input_interpretation |

## Response Metadata Completeness (8.8)

Every successful response MUST include:

- [ ] request_id (UUID)
- [ ] original_query
- [ ] input_mode
- [ ] input_interpretation (from_query, from_params, conflicts, resolution)
- [ ] filters_applied
- [ ] total_studies_analyzed
- [ ] api_calls (with endpoint, params, status, duration)
- [ ] stage_timings
- [ ] api_version
- [ ] data_refresh
- [ ] source = "clinicaltrials.gov"

## Logging Verification

| #   | Verify                                                                                   |
| --- | ---------------------------------------------------------------------------------------- |
| 9.1 | pipeline_start + stage_completes + api_calls + llm_calls + pipeline_complete all present |
| 9.2 | All log entries share same request_id                                                    |
| 9.3 | API calls logged with endpoint, params, status, record_count, duration_ms                |
| 9.4 | LLM calls logged with model, tokens, duration, output_valid                              |
| 9.5 | Validation failures logged with field + valid_values                                     |

## Viz Spec Verification

| #    | Verify                                                    |
| ---- | --------------------------------------------------------- |
| 10.1 | encoding structure matches type_category contract         |
| 10.2 | encoding field names exist in data columns                |
| 10.3 | type is specific ("bar_chart" not "chart")                |
| 10.4 | title references actual entities                          |
| 10.5 | rendering_hints has color_scheme                          |
| 10.6 | data matches aggregated output exactly — no invented rows |
