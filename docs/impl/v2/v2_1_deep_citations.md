# V2.1 — Deep Citations (15 min)

**What exists:** Aggregator accepts `include_citations=True`, collects `nct_id` + `excerpt` per group. `spec.data = aggregated_data` injection in viz_generator.

---

## The Change

In `app/pipeline/viz_generator.py` `generate()`:

```python
# BEFORE building LLM prompt — strip citations (don't mutate originals)
data_for_prompt = [
    {k: v for k, v in row.items() if k != "citations"}
    for row in aggregated_data
]

# Use data_for_prompt (clean) when building the prompt for the LLM
# ... existing LLM call with data_for_prompt ...

# AFTER getting spec — inject full data WITH citations
spec.data = aggregated_data  # this line already exists
                              # just ensure aggregated_data is not mutated above
```

**CRITICAL: do NOT use `row.pop("citations")` — it mutates the original list. Use dict comprehension.**

## Verify

1. In `orchestrator.py`: confirm `aggregate()` receives `include_citations=request.include_citations` and `max_citations_per_group=request.max_citations_per_group`
2. In `aggregator.py`: confirm when `include_citations=True`, each row in returned list has a `citations` key
3. In `viz_generator.py`: confirm `spec.data = aggregated_data` happens AFTER the LLM call

## Test

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"Pembrolizumab trials by phase","include_citations":true,"max_citations_per_group":3}' \
  | python3 -c "
import sys, json; d=json.load(sys.stdin)
for row in d['visualizations'][0]['data'][:3]:
    cites = row.get('citations',[])
    print(f'{row.get(\"phase_label\",\"?\")}: {len(cites)} citations')
    for c in cites[:2]:
        print(f'  - {c[\"nct_id\"]}: {c[\"excerpt\"][:60]}')
"
```

Expected: each data row has `citations` list with up to 3 entries, each with `nct_id` and `excerpt`.
