# V2.5 — Free-Text Extraction / Stage 2.5 (45 min)

**Only implement if V2.1-V2.4 are done.** MVP scope: individual extraction only (≤20 records).

---

## New File: `app/pipeline/extractor.py`

```python
from app.schemas.intent import ExtractionSpec
from app.schemas.trial_record import StudyRecord
from app.utils.logger import get_logger, log_event
import json
import logging
from openai import AsyncOpenAI

logger = get_logger(__name__)

async def extract_from_records(
    records: list[StudyRecord],
    spec: ExtractionSpec,
    request_id: str | None = None,
    model: str = "gpt-4o-mini",
) -> list[dict]:
    """Extract structured data from free-text fields.
    Returns list of {nct_id, <extract_as>: value}.
    Only processes first 20 records (individual mode)."""

    capped = records[:20]
    sampled = len(records) > 20

    if sampled:
        log_event(logger, logging.WARNING, "extraction_sampled",
            request_id=request_id,
            total=len(records), sample_size=20)

    results = []
    client = AsyncOpenAI()

    for record in capped:
        source_text = getattr(record, spec.source_field, record.excerpt)
        if not source_text:
            results.append({"nct_id": record.nct_id, spec.extract_as: None})
            continue

        prompt = f"""Extract the following from this clinical trial description.
What to extract: {spec.extraction_prompt}
Return JSON: {{"nct_id": "{record.nct_id}", "{spec.extract_as}": <extracted value or null if not found>}}
Do not invent data. If the information is not present, return null.

Description:
{source_text[:2000]}"""

        try:
            response = await client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200
            )
            parsed = json.loads(response.choices[0].message.content)
            parsed["nct_id"] = record.nct_id  # ensure correct nct_id
            results.append(parsed)
        except Exception as e:
            log_event(logger, logging.WARNING, "extraction_error",
                request_id=request_id,
                nct_id=record.nct_id, error=str(e))
            results.append({"nct_id": record.nct_id, spec.extract_as: None})

    log_event(logger, logging.INFO, "extraction_complete",
        request_id=request_id,
        records_processed=len(capped),
        non_null=sum(1 for r in results if r.get(spec.extract_as) is not None))

    return results
```

## Wire Into Orchestrator

Between Stage 2 (data retrieval) and Stage 3 (aggregation), in the per-task loop:

```python
import pandas as pd
from app.pipeline.extractor import extract_from_records

# In the per-task loop, after getting studies:
if task.extraction and task.extraction.needed:
    with timed_stage(logger, ctx, f"extraction_{task.task_id}"):
        extracted = await extract_from_records(
            studies,
            task.extraction,
            ctx.request_id,
            model=settings.llm_model_extractor
        )

        if len(studies) > 20:
            ctx.add_limitation(
                f"Extraction applied to first 20 of {len(studies)} records (sample)")

        # Merge extracted fields into study data for aggregation
        df_studies = pd.DataFrame([s.model_dump() for s in studies[:len(extracted)]])
        df_extracted = pd.DataFrame(extracted)
        df_merged = df_studies.merge(df_extracted, on="nct_id", how="left")

        # Use merged data as dicts for aggregation
        merged_records = df_merged.to_dict(orient="records")

        # Aggregate using the merged data (includes extracted field)
        aggregated = _aggregate_from_dicts(
            merged_records, task.aggregation,
            include_citations=request.include_citations,
            max_citations_per_group=request.max_citations_per_group
        )
else:
    # existing path: aggregate from StudyRecords
    aggregated = aggregate(studies, task.aggregation, ...)
```

## Aggregator Must Handle Dict Input

Add a helper that accepts `list[dict]` instead of `list[StudyRecord]`:

```python
# In aggregator.py
def aggregate_from_dicts(
    records: list[dict],
    spec: AggregationSpec,
    include_citations: bool = False,
    max_citations_per_group: int = 5
) -> list[dict]:
    """Same as aggregate() but accepts raw dicts (for enriched/merged data)."""
    df = pd.DataFrame(records)
    # ... same logic as _aggregated() ...
```

OR refactor `aggregate()` to accept both:

```python
def aggregate(records, spec, ...):
    if records and isinstance(records[0], dict):
        df = pd.DataFrame(records)
    else:
        df = pd.DataFrame([r.model_dump() for r in records])
    # ... rest unchanged ...
```

The second approach is simpler — one function handles both cases.

## What Stage 1 Needs to Produce

For extraction to trigger, Stage 1 must set `ExtractionSpec.needed = True`. The query analyzer prompt already includes extraction instructions. Example intent for a dosage query:

```json
{
  "extraction": {
    "needed": true,
    "source_field": "excerpt",
    "extract_as": "dosage",
    "extraction_prompt": "the drug dosage and unit for Pembrolizumab",
    "expected_type": "str"
  },
  "aggregation": {
    "group_by": ["dosage"],
    "metric": "count",
    "output_mode": "aggregated"
  }
}
```

## Test

```bash
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "What dosages of Pembrolizumab are being studied in Phase 3 trials?",
    "trial_phase": "PHASE3",
    "max_studies": 20
  }' | python3 -c "
import sys, json; d=json.load(sys.stdin)
print('viz type:', d['visualizations'][0]['type'])
for row in d['visualizations'][0]['data'][:5]:
    print(f'  {row}')
print('notes:', d['meta'].get('notes'))
print('limitations:', d['meta'].get('limitations'))
"
```

Expected: data rows show extracted dosages grouped and counted. If >20 studies matched, limitation notes the sample.

## Limitations (document honestly)

- Individual extraction only (≤20 records). Batch mode is v3.
- Extraction quality depends on the source text. Some study descriptions don't mention dosages.
- Each extraction is a separate LLM call — 20 records = 20 calls. This adds significant latency (~30s total).
- Extracted field is a dynamic string, not validated against a schema.
