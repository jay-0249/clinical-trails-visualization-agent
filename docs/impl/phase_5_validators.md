**File to update:** `app/utils/validators.py`

---

## Functions to implement

```python
def validate_structured_hints(request: QueryRequest, cache: ReferenceDataCache) -> None:
    """Validate trial_phase and trial_status against cached enums.
    Called BEFORE the LLM runs. Raises 400 with valid values on failure."""

def validate_intent(intent: QueryIntent, cache: ReferenceDataCache) -> None:
    """Validate LLM-produced QueryIntent against reference data.
    Called AFTER Stage 1, BEFORE Stage 2."""
```

## validate_structured_hints checks

- If `trial_phase` is provided, it must be in `cache.valid_phases`
- If `trial_status` is provided, it must be in `cache.valid_statuses`
- On failure: raise HTTPException(400) with valid values listed

## validate_intent checks

- `filter_params` values against cached enums
- `aggregation.group_by` fields exist on StudyRecord (use `cache.groupable_fields`)
- `aggregation.metric_field` exists on StudyRecord when metric is sum/collect/unique_count
- `candidate_viz_categories` are valid Literal values
- `output_mode` consistency:
  - `raw_records` only valid when `distribution` in candidates
  - `edge_list` only valid when `relational` in candidates
  - `edge_list` requires exactly 2 fields in `group_by`
- Task count ≤ 4
- Data requirement count ≤ 5
- Clear error messages listing valid values on failure

---

## Test: `tests/test_validators.py`

Test cases 3.1-3.8 from `tests/test_validators.py`. Mock reference cache with known values.
