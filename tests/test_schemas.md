test_schemas (Phase 1)

| #   | Scenario                                                       | Expected                              |
| --- | -------------------------------------------------------------- | ------------------------------------- |
| 1   | QueryRequest rejects query < 3 chars                           | 422 validation error                  |
| 2   | QueryRequest rejects invalid input_mode                        | 422 validation error                  |
| 3   | QueryRequest accepts valid input with all fields               | Pass                                  |
| 4   | QueryRequest accepts minimal input (query only)                | Pass, all optionals None              |
| 5   | AggregationSpec validates output_mode values                   | Only aggregated/raw_records/edge_list |
| 6   | AggregationSpec rejects invalid output_mode                    | Validation error                      |
| 7   | VisualizationSpec.type accepts any string                      | "heatmap", "custom_chart" both valid  |
| 8   | VisualizationSpec.type_category rejects invalid                | Only 7 Literal values                 |
| 9   | AnalysisTask.candidate_viz_categories rejects invalid          | Only 7 Literal values                 |
| 10  | All models round-trip: construct → model_dump → model_validate | Identical                             |
| 11  | StudyRecord with all None optionals is valid                   | Pass                                  |
| 12  | PipelineContext has request_id field                           | Field exists, required                |
| 13  | ErrorResponse has all required fields                          | error, message required               |
