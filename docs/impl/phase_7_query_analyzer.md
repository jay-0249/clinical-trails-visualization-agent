# Phase 7: Query Analyzer (Stage 1 LLM)

**Files to create:**

- `app/prompts/query_analyzer.py` — prompt template + builder functions
- `app/pipeline/query_analyzer.py` — `analyze()` function

**Reference:** Prompt template and builder function are already in `app/prompts/query_analyzer.py`. Read that file directly.

---

## Prompt builder

```python
# app/prompts/query_analyzer.py
# Prompt version: 2026-07-21-a

def build_query_analyzer_prompt(
    valid_enums, groupable_fields, tool_schemas,
    input_mode, confirmed_filters
) -> str:
    """Assemble the Stage 1 system prompt with runtime data."""
    # Inject: valid_phases, valid_statuses, valid_sponsor_classes
    # Inject: groupable_fields list
    # Inject: tool_schemas JSON
    # Inject: mode_instruction (from build_mode_instruction)
    # Inject: confirmed_filters JSON
    # Inject: QueryIntent JSON schema

def build_mode_instruction(input_mode: str) -> str:
    """Return mode-specific instructions for supplement/override/query_only."""
```

See `docs/PROMPTS.md` for the complete prompt template with all sections.

## Analyzer function

```python
# app/pipeline/query_analyzer.py

async def analyze(
    query: str,
    confirmed_filters: dict,
    input_mode: str,
    reference_cache: ReferenceDataCache
) -> QueryIntent:
    # 1. Build prompt using builder
    # 2. Call LLM with structured output / function calling
    # 3. Parse response as JSON
    # 4. Validate with Pydantic: QueryIntent.model_validate(data)
    # 5. Log: model, tokens, duration, output_valid
    # 6. Return validated QueryIntent
```

## LLM calling

Use LangChain's ChatOpenAI or ChatAnthropic based on config.

Use structured output to get JSON matching QueryIntent schema.

If output is invalid, log the failure and retry once with a clearer instruction.

---

## Manual testing

Run these queries and inspect the output:

1. "How are Pembrolizumab trials distributed across phases?" → categorical, single data req
2. "Compare Pembrolizumab vs Nivolumab by phase" → comparative, 2 data reqs with entity_tags
3. `query="show me", drug_name="Pembrolizumab", input_mode="override"` → inferred intent from params
4. "Show a network of sponsors and drugs for breast cancer" → relational, edge_list output_mode
