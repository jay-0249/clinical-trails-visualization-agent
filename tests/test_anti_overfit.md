These queries are NOT in the problem statement examples. Every one must produce a valid response WITHOUT any code changes. If any fails, the system is overfit.

| # | Query | Must work |
| --- | --- | --- |
| 6.1 | "How are Trastuzumab trials distributed across phases?" | Same pipeline as any drug |
| 6.2 | "Show trial trends for Crohn's disease since 2010" | temporal, no condition-specific path |
| 6.3 | "Enrollment distribution for Phase 3 cancer trials" | distribution category, raw_records |
| 6.4 | "Sponsor types over time for diabetes" | matrix category (heatmap) |
| 6.5 | "Break down breast cancer by sponsor_class > sponsor > drug" | hierarchical category |
| 6.6 | "Countries with most recruiting HIV trials" | spatial or categorical |
| 6.7 | "Drugs that co-occur in lymphoma combination studies" | relational, edge_list |
| 6.8 | "Phase 3 Pembrolizumab by phase AND geographic distribution" | 2 tasks, 1 data req |
| 6.9 | `query="show me", drug_name="Pembrolizumab", input_mode="override"` | Reasonable default, no crash |
| 6.10 | "Most common study types for Alzheimer's trials" | group_by=study_type works |

## Input Mode Tests

| # | Scenario | Expected |
| --- | --- | --- |
| 5.1 | Supplement, no conflict | Both used, no conflict logged |
| 5.2 | Supplement, query="Nivolumab", drug_name="Pembrolizumab" | Param wins, conflict logged |
| 5.3 | Supplement, comparison + one hint | TWO data reqs, hint on one arm only |
| 5.4 | Override, specific params | Filters from params only |
| 5.5 | Override, comparison query but single param | Single-entity + warning |
| 5.6 | Query only, params provided but ignored | Query used, ignored params logged |
| 5.7 | Query only, no params | Normal processing |
| 5.8 | Supplement, query has extra entities | Hint confirms one arm, query provides second |

## Error Handling

| # | Scenario | Expected |
| --- | --- | --- |
| 7.1 | Zero API results (nonexistent drug) | Empty viz, noted in metadata |
| 7.2 | Query too short `{"query": "hi"}` | 422 validation error |
| 7.3 | Invalid enum `{"trial_phase": "PHASE99"}` | 400 with valid values |
| 7.4 | Large result truncation | Fetches up to cap, notes limitation |