# V2.3 — field_stats Full Implementation (30 min)

---

## Step 1: Verify API Response Shape FIRST

Before writing any code, make a live call and print the response:

```bash
curl -s "https://clinicaltrials.gov/api/v2/stats/field/values?field=Phase" | python3 -m json.tool | head -30
```

Print the response and confirm the structure before implementing the parser.

## Step 2: Field Name Mapping

Our StudyRecord fields don't match the API's stat field names. Explicit mapping:

```python
_GROUPBY_TO_STATS_FIELD = {
    "phase_label": "Phase",
    "phases": "Phase",
    "status": "OverallStatus",
    "sponsor_class": "LeadSponsorClass",
    "study_type": "StudyType",
    "intervention_types": "InterventionType",
}
```

If `group_by[0]` is NOT in this map, field_stats CANNOT handle it — fall back to study_search with a note.

This is a closed set mapping to a fixed API surface, not overfitting.

## Step 3: In `data_retriever.py` — Implement Real Path

Remove the fallback-to-study_search for field_stats. Implement the actual call:

```python
if requirement.retrieval_strategy == "field_stats":
    stats_field = _resolve_stats_field(requirement, task)
    if stats_field:
        stats = await ct_client.get_field_stats(stats_field, requirement.filter_params)
        ctx.add_field_stats(stats)
    else:
        # Can't map to stats field — fall back
        log_event(logger, logging.WARNING, "field_stats_fallback",
            request_id=ctx.request_id,
            reason=f"No stats field mapping for {requirement}")
        # ... fall back to study_search ...
```

## Step 4: In `orchestrator.py` — Skip Aggregator

field_stats data is already aggregated by the API. Don't send it through `aggregate()`:

```python
if "field_stats" in strategies:
    raw_stats = ctx.get_field_stats()
    group_by_field = task.aggregation.group_by[0]

    aggregated = [
        {group_by_field: stat.field_value, "count": stat.count}
        for stat in raw_stats
    ]

    # Sort to match aggregator behavior
    aggregated.sort(key=lambda x: x["count"], reverse=True)

    # Citations impossible with field_stats
    if request.include_citations:
        ctx.add_limitation(
            "Citations unavailable with field_stats strategy "
            "(no individual records fetched)")
else:
    # existing study_search → aggregate path
```

## Step 5: Validate When field_stats Is Appropriate

Keep study_search (don't use field_stats) when:

- `include_citations=True` AND citations actually needed
- Multiple `group_by` fields (cross-tabulation)
- `output_mode` is `edge_list` or `raw_records`
- Comparison queries (entity_tags present)
- `group_by[0]` not in `_GROUPBY_TO_STATS_FIELD`

Add this check in the orchestrator. If field_stats is invalid for the query, fall back to study_search with a note in metadata.

## Test

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"How are all cancer trials distributed across phases?"}' \
  | python3 -c "
import sys,json; d=json.load(sys.stdin); m=d['meta']
print('strategy:', m.get('data_retrieval_strategy'))
print('studies:', m.get('total_studies_analyzed'))
for row in d['visualizations'][0]['data']:
    print(f'  {row}')
"
```

Expected: strategy shows field_stats (or study_search with note), data has phase counts covering potentially 100K+ trials.
