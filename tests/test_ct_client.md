test_ct_client (Phase 3)

## Normalization Tests (fixture data, no live API)

| #    | Scenario                                 | Verify                                  |
| ---- | ---------------------------------------- | --------------------------------------- |
| 2.1  | Complete study record                    | All StudyRecord fields mapped correctly |
| 2.2  | Minimal record (nctId + briefTitle only) | No crash, None/empty defaults           |
| 2.3  | Multi-phase `["PHASE1", "PHASE2"]`       | `phase_label = "Phase 1/Phase 2"`       |
| 2.4  | Single phase `["PHASE3"]`                | `phase_label = "Phase 3"`               |
| 2.5  | No phase `[]` or null                    | `phase_label = "N/A"`                   |
| 2.6  | 3 locations, 2 countries                 | `countries` has unique names            |
| 2.7  | Null locations                           | `countries=[], cities=[]`               |
| 2.8  | 3 interventions                          | 3 names, 3 types extracted              |
| 2.9  | Enrollment present `{"count": 150}`      | `enrollment = 150`                      |
| 2.10 | Enrollment null                          | `enrollment = None`                     |

## Integration Test (`@pytest.mark.integration`)

| #    | Scenario                                    | Verify                                                            |
| ---- | ------------------------------------------- | ----------------------------------------------------------------- |
| 2.11 | Fetch 2 Pembrolizumab studies from live API | Returns list[StudyRecord], all fields populated or None, no crash |
