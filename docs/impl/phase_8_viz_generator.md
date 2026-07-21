# Phase 8: Viz Generator (Stage 4 LLM)

**Files to create:**

- `app/prompts/viz_generator.py` — prompt template + builder
- `app/pipeline/viz_generator.py` — `generate()` function

**Reference:** Prompt template and builder function are already in `app/prompts/viz_generator.py`. Read that file directly.

---

## Prompt builder

```python
# app/prompts/viz_generator.py
# Prompt version: 2026-07-21-a

def build_viz_generator_prompt(
    task: AnalysisTask,
    aggregated_data: list[dict],
    original_query: str,
) -> str:
    # Inject: task_id, task_description, candidate_categories
    # Inject: aggregated_data (cap at 50 rows for prompt size)
    # Inject: data_row_count
    # Inject: original_query
    # Inject: VisualizationSpec JSON schema
    # Include: all 7 encoding contracts
    # Include: type selection reasoning guidelines
```

## Generator function

```python
# app/pipeline/viz_generator.py

async def generate(
    task: AnalysisTask,
    aggregated_data: list[dict],
    original_query: str,
) -> VisualizationSpec:
    # 1. Build prompt
    # 2. Call LLM with structured output
    # 3. Parse and validate with Pydantic
    # 4. Verify encoding matches type_category contract
    # 5. Verify encoding field names exist in data columns
    # 6. Log: model, tokens, duration, type chosen, type_category
    # 7. Return VisualizationSpec
```

## Key rules for the LLM

1. NEVER invent data — data field must match aggregated input exactly
2. type is OPEN string — any chart type is valid
3. type_category must be from the 7 Literals
4. encoding must follow the category's contract
5. description must JUSTIFY the type choice
6. title must be specific ("Phase Distribution of Pembrolizumab" not "Bar Chart")
7. rendering_hints should include at least color_scheme

---

## Manual testing

Feed different data shapes and verify type selection:

- Phase count data → categorical
- Year-count pairs → temporal
- Source-target-weight edges → relational
- Two-dimensional counts → matrix (should pick heatmap, not grouped bar)
- Raw enrollment values → distribution
