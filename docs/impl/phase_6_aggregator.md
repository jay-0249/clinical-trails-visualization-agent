**File to create:** `app/pipeline/aggregator.py`

This is the MOST IMPORTANT deterministic component. It must be fully generic — no field names in branching logic.

---

## Entry point

```python
def aggregate(
    records: list[StudyRecord],
    spec: AggregationSpec,
    include_citations: bool = False,
    max_citations_per_group: int = 5
) -> list[dict]:
    if spec.output_mode == "raw_records":
        return _raw_records(records, spec, include_citations)
    elif spec.output_mode == "edge_list":
        return _edge_list(records, spec, include_citations)
    else:
        return _aggregated(records, spec, include_citations, max_citations_per_group)
```

## Aggregated mode

Used by: categorical, temporal, spatial, matrix, hierarchical

1. Convert records to DataFrame: `pd.DataFrame([r.model_dump() for r in records])`
2. For each field in `group_by`: if the column contains lists, `df.explode(col)`
3. If `time_granularity` is set and grouping by time field, ensure proper sorting
4. `grouped = df.groupby(spec.group_by, dropna=False)`
5. Apply metric:
   - `count`: `grouped.size()`
   - `sum`: `grouped[spec.metric_field].sum()`
   - `unique_count`: `grouped[spec.metric_field].nunique()`
   - `collect`: `grouped[spec.metric_field].apply(list)`
6. Replace NaN group keys with `"Unknown"`
7. Sort by `spec.sort_by` (value_desc, value_asc, key_desc, key_asc)
8. If `include_citations`: collect nct_id + excerpt per group, cap at max_citations_per_group
9. Return `result.to_dict(orient="records")`

## Raw records mode

Used by: distribution (histogram, box plot, scatter)

1. Extract `spec.metric_field` value from each record
2. Return `[{"value": val, "nct_id": r.nct_id} for r in records if val is not None]`
3. For scatter plots: include additional fields from `spec.group_by`

## Edge list mode

Used by: relational (network, chord, sankey)

1. `group_by` has exactly 2 fields: `[source_field, target_field]`
2. For each record, get values of both fields (may be lists)
3. Generate all pairs: `source_values × target_values`
4. Count co-occurrences across all records
5. Return `[{"source": s, "target": t, "weight": count}]`
6. If `include_citations`: collect nct_ids per edge

## Anti-overfit verification

After implementing, verify:

- No field names like `phase_label` or `sponsor_name` appear in if/elif branching
- The same function handles `group_by=["study_type"]` as `group_by=["phase_label"]`
- Empty input returns `[]`

---

## Test: `tests/test_aggregator.py`

Test cases 4.1-4.15 from `tests/test_aggregator.py`. Use fixture StudyRecord objects.

Add one extra test with `group_by=["study_type"]` (field not used in examples).
