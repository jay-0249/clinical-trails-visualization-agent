test_aggregator (Phase 6)
MOST IMPORTANT TEST FILE. Use fixture StudyRecord objects, no API or LLM needed.

## Aggregated Mode

| #    | Scenario                                                               | Verify                                                           |
| ---- | ---------------------------------------------------------------------- | ---------------------------------------------------------------- |
| 4.1  | Single field count, 10 records                                         | One row per unique value, counts sum to 10                       |
| 4.2  | Multi-field count `["phase_label", "sponsor_class"]`                   | One row per pair                                                 |
| 4.3  | List field explosion: countries `[["US","UK"],["US"],["UK","France"]]` | US=2, UK=2, France=1                                             |
| 4.4  | Sum metric on enrollment                                               | Sum per group                                                    |
| 4.5  | Unique count metric on conditions                                      | Distinct values per group                                        |
| 4.6  | Time granularity year                                                  | Sorted by year ascending                                         |
| 4.7  | Sort descending                                                        | Rows sorted by metric value desc                                 |
| 4.8  | Null values in group field                                             | "Unknown" group, no crash                                        |
| 4.9  | Empty records list `[]`                                                | Returns `[]`, no crash                                           |
| 4.10 | Citations included, max 2                                              | Each group has citations list, max 2, each with nct_id + excerpt |

## Raw Records Mode

| #    | Scenario               | Verify                               |
| ---- | ---------------------- | ------------------------------------ |
| 4.11 | Raw enrollment values  | List of `{value, nct_id}` per record |
| 4.12 | Null enrollment values | Excluded or null, no crash           |

## Edge List Mode

| #    | Scenario                                                  | Verify                             |
| ---- | --------------------------------------------------------- | ---------------------------------- |
| 4.13 | Simple co-occurrence (sponsor × interventions)            | `{source, target, weight}` triples |
| 4.14 | List field: sponsor="Pfizer", interventions=["A","B","C"] | 3 edges                            |
| 4.15 | Weight accumulation: 3 records same sponsor+drug          | Single edge weight=3               |

## Anti-Overfit Extra

| #    | Scenario                                          | Verify                     |
| ---- | ------------------------------------------------- | -------------------------- |
| 4.16 | `group_by=["study_type"]` (field NOT in examples) | Works without code changes |
