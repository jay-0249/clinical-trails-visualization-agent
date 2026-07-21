CT.gov v2 has no simple year range param. Post-filter StudyRecords after retrieval.

---

## Where

In `orchestrator.py`, in the per-task loop, AFTER `ctx.get_studies_by_tags()`, BEFORE `aggregate()`.

## Implementation

```python
def _apply_year_filters(
    studies: list[StudyRecord],
    request: QueryRequest,
    ctx: PipelineContext
) -> list[StudyRecord]:
    if not request.start_year and not request.end_year:
        return studies

    before_count = len(studies)
    filtered = studies

    if request.start_year:
        filtered = [s for s in filtered
                    if s.start_year is not None and s.start_year >= request.start_year]
    if request.end_year:
        filtered = [s for s in filtered
                    if s.start_year is not None and s.start_year <= request.end_year]

    after_count = len(filtered)

    if after_count == 0 and before_count > 0:
        ctx.add_warning(
            f"All {before_count} studies filtered out by year range "
            f"{request.start_year}-{request.end_year}")
    elif after_count < before_count:
        ctx.add_note(
            f"Year filter {request.start_year or 'any'}-{request.end_year or 'any'}: "
            f"{before_count} -> {after_count} studies")

    return filtered
```

## Edge Cases

- Records with `start_year=None` are excluded — can't verify in range
- If ALL records filtered out: warning added, aggregator receives empty list, returns empty result
- Both params optional — can filter by just start or just end

## Also Update `build_meta()`

```python
if request.start_year:
    filters_applied["start_year_gte"] = request.start_year
if request.end_year:
    filters_applied["end_year_lte"] = request.end_year
```

## Test

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Lung cancer trials by phase","start_year":2020,"end_year":2025}' \
  | python3 -c "
import sys,json; d=json.load(sys.stdin); m=d['meta']
print('filters:', m.get('filters_applied'))
print('notes:', m.get('notes'))
print('studies:', m.get('total_studies_analyzed'))
"
```
