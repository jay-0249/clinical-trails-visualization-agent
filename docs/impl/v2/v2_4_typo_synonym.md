# V2.4 — Typo/Synonym Normalization (30 min)

Optional LLM call between Stage 1 and Stage 2 that resolves drug/condition synonyms.

---

## New Request Param

In `app/schemas/request.py` QueryRequest:

```python
normalize_entities: bool = Field(
    False,
    description="Resolve drug/condition synonyms via LLM (e.g. Keytruda → Pembrolizumab)"
)
```

## Normalizer Prompt (must be tight)

```
You resolve drug and condition names to their canonical ClinicalTrials.gov forms.
Rules:
- Brand names → generic names (Keytruda → Pembrolizumab, Opdivo → Nivolumab)
- Common names → MeSH terms ONLY if confident (lung cancer → Lung Neoplasms)
- If already canonical or unsure, return UNCHANGED
- Never invent names. If you don't know the canonical form, return the original.
- Return a JSON array of the same length as input, same order.

Input: {originals_json}
Output:
```

## Implementation in `orchestrator.py`

```python
async def _normalize_entities(
    intent: QueryIntent,
    request_id: str,
    settings: Settings
) -> tuple[QueryIntent, list[str]]:
    """Returns (modified intent, list of change descriptions)."""
    entities = []
    for req in intent.data_requirements:
        for param_key in ("intr", "cond"):
            val = req.search_params.get(param_key)
            if val:
                entities.append({
                    "req_id": req.requirement_id,
                    "param": param_key,
                    "original": val
                })

    if not entities:
        return intent, []

    originals = [e["original"] for e in entities]

    # Call LLM with extractor model
    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model=settings.llm_model_extractor,
        response_format={"type": "json_object"},
        messages=[{
            "role": "user",
            "content": NORMALIZER_PROMPT.replace("{originals_json}", json.dumps(originals))
        }],
        max_tokens=200
    )

    # Parse response
    result = json.loads(response.choices[0].message.content)
    # Handle both {"names": [...]} and bare [...] formats
    normalized = result if isinstance(result, list) else result.get("names", originals)

    # Validate: same length
    if len(normalized) != len(originals):
        return intent, []  # LLM returned wrong shape, skip normalization

    # Apply changes
    changes = []
    for entity_info, new_name in zip(entities, normalized):
        old = entity_info["original"]
        if new_name and isinstance(new_name, str) and new_name != old:
            changes.append(f"{old} \u2192 {new_name}")
            for req in intent.data_requirements:
                if req.requirement_id == entity_info["req_id"]:
                    req.search_params[entity_info["param"]] = new_name

    return intent, changes
```

## Wire Into Orchestrator

After Stage 1 (query analysis), before merge:

```python
# After validate_intent, before merge_and_validate
if request.normalize_entities:
    with timed_stage(logger, ctx, "entity_normalization"):
        intent, changes = await _normalize_entities(
            intent, ctx.request_id, settings
        )
        if changes:
            ctx.add_note(f"Entity normalization: {', '.join(changes)}")
        else:
            ctx.add_note("Entity normalization: no changes needed")
```

## Use `llm_model_extractor` — This Is a Simple Lookup, Not Reasoning

## Test

```bash
# Should normalize Keytruda → Pembrolizumab
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"How are Keytruda trials distributed across phases?","normalize_entities":true}' \
  | python3 -c "
import sys,json; d=json.load(sys.stdin); m=d['meta']
print('filters:', m.get('filters_applied'))
print('notes:', m.get('notes'))
"

# Should NOT normalize (already canonical)
curl -s -X POST http://localhost:8000/api/v1/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"How are Pembrolizumab trials distributed across phases?","normalize_entities":true}' \
  | python3 -c "
import sys,json; d=json.load(sys.stdin); m=d['meta']
print('notes:', m.get('notes'))
"
```

Expected: first query shows `Pembrolizumab` in filters (not Keytruda), notes show normalization. Second query shows "no changes needed".
