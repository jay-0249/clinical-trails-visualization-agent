# Phase 9: Orchestrator + Data Retriever

**Files to create:**

- `app/pipeline/orchestrator.py` — main pipeline + merge function
- `app/pipeline/data_retriever.py` — translates DataRequirement to ct_client calls

---

## data_retriever.py

Translates the abstract `DataRequirement` from QueryIntent into concrete `ct_client` calls.

```python
async def fetch_data(
    requirement: DataRequirement,
    ct_client: CTGovClient,
    ctx: PipelineContext,
    max_records: int
) -> None:
    """Fetch data per requirement and add to context."""
    if requirement.retrieval_strategy == "field_stats":
        stats = await ct_client.get_field_stats(...)
        ctx.add_field_stats(stats)
    elif requirement.retrieval_strategy == "study_detail":
        record = await ct_client.get_study_detail(...)
        ctx.add_studies([record])
    else:  # study_search
        # Map search_params to query.* params
        # Map filter_params to filter.* params
        # Call ct_client.search_studies with pagination
        # Handle truncation
        records, truncation = await ct_client.search_studies(...)
        ctx.add_studies(records, entity_tag=requirement.entity_tag)
        if truncation:
            ctx.add_limitation(f"...")
```

## orchestrator.py

The main pipeline. Contains `execute()` and `merge_and_validate()`.

```python
async def execute(request: QueryRequest, reference_cache, ct_client) -> PipelineResponse:
    request_id = str(uuid.uuid4())
    ctx = PipelineContext(request_id=request_id, ...)

    log pipeline_start

    # Pre-validate structured hints
    validate_structured_hints(request, reference_cache)

    # Stage 1: Query Analysis (LLM)
    with timed_stage(logger, ctx, "query_analysis"):
        intent = await query_analyzer.analyze(...)
        validate_intent(intent, reference_cache)

    # Merge structured hints based on input_mode
    intent, interpretation = merge_and_validate(intent, request, ctx)

    # Stage 2: Data Retrieval
    with timed_stage(logger, ctx, "data_retrieval"):
        for req in intent.data_requirements:
            await data_retriever.fetch_data(req, ct_client, ctx, request.max_studies)

    # Stage 3 + 4: Per-task processing
    visualizations = []
    for task in intent.tasks:
        # Get relevant studies for this task
        req_ids = intent.task_data_map[task.task_id]
        tags = [r.entity_tag for r in intent.data_requirements if r.requirement_id in req_ids]
        studies = ctx.get_studies_by_tags(tags) if any(tags) else ctx.get_all_studies()

        # Stage 3: Aggregate
        with timed_stage(logger, ctx, f"aggregation_{task.task_id}"):
            aggregated = aggregate(studies, task.aggregation, ...)

        # Stage 4: Viz Spec (LLM)
        with timed_stage(logger, ctx, f"viz_generation_{task.task_id}"):
            viz = await viz_generator.generate(task, aggregated, intent.original_query)

        visualizations.append(viz)

    log pipeline_complete
    return PipelineResponse(visualizations=visualizations, meta=build_meta(...))
```

## merge_and_validate function

Lives in `orchestrator.py`. Returns `tuple[QueryIntent, InputInterpretation]`.

Three modes:

- **query_only:** skip merge, log ignored params
- **override:** replace ALL search/filter params with structured hints, keep only analysis intent. Collapse comparison to single-entity if only one entity in params.
- **supplement:** smart merge with conflict detection. For comparisons, only apply hints to the matching arm (check entity_tag). Log conflicts.

See `docs/DESIGN.md` Input Mode section for the full implementation.

---

## Manual testing

End-to-end: send a query and verify the full pipeline produces a response with all metadata fields populated.
