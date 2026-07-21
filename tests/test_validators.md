test_validators (Phase 5)
Mock reference cache with known enum values for all tests.

| #   | Scenario                                       | Expected                                 |
| --- | ---------------------------------------------- | ---------------------------------------- |
| 3.1 | Valid intent with correct enums and fields     | Pass                                     |
| 3.2 | Invalid phase `"Phase3"` (wrong format)        | Error listing valid phases               |
| 3.3 | Invalid group_by field `"nonexistent_field"`   | Error listing valid fields               |
| 3.4 | 5 tasks (max is 4)                             | Error                                    |
| 3.5 | 6 data requirements (max is 5)                 | Error                                    |
| 3.6 | edge_list with 1 group_by field (needs 2)      | Error                                    |
| 3.7 | raw_records without distribution in candidates | Error                                    |
| 3.8 | `trial_phase="PHASE99"` in QueryRequest        | 400 before LLM runs, valid phases listed |
