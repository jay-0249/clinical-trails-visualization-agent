# Phase 10: FastAPI Endpoint + Examples

**Files to create/update:**

- `app/main.py` — FastAPI app
- `examples/*.json` — 3-5 example runs
- `README.md` — full documentation

---

## main.py

```python
from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: load reference cache
    await reference_cache.load()
    yield
    # Shutdown: cleanup

app = FastAPI(title="CT.gov Viz Agent", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "api_version": reference_cache.api_version,
        "cache_loaded": reference_cache.is_loaded,
        "data_refresh": reference_cache.last_refresh
    }

@app.post("/api/v1/query", response_model=PipelineResponse)
async def query(request: QueryRequest):
    try:
        return await orchestrator.execute(request, reference_cache, ct_client)
    except ValidationError as e:
        raise HTTPException(400, detail=ErrorResponse(
            error="validation_error", message=str(e),
            suggestion="Check field values against valid options"
        ).model_dump())
    except Exception as e:
        logger.exception("pipeline_error")
        raise HTTPException(500, detail=ErrorResponse(
            error="internal_error", message="An unexpected error occurred",
            details={"type": type(e).__name__}
        ).model_dump())
```

## Example runs

Generate 5 examples by calling the running API:

1. `{"query": "How are Pembrolizumab trials distributed across phases?"}` → save response
2. `{"query": "How has the number of trials for lung cancer changed per year since 2015?"}` → save response
3. `{"query": "Compare phases for trials involving Pembrolizumab vs Nivolumab"}` → save response
4. `{"query": "Which countries have the most recruiting trials for diabetes?"}` → save response
5. `{"query": "Show a network of sponsors and drugs for breast cancer trials"}` → save response

Save actual JSON output to `examples/example_N_description.json`.

## README.md

Must include:

- How to install (`pip install -r requirements.txt`)
- How to configure (`.env` file)
- How to run (`uvicorn app.main:app --port 8000`)
- Request schema with all fields documented
- Response schema with all fields documented
- Key design decisions (reference docs/DECISIONS.md)
- Architecture overview (pipeline diagram)
- Limitations and future improvements
- AI tools used and validation approach

---

## Test: `tests/test_pipeline_e2e.py`

Use FastAPI TestClient:

- Test cases 8.1-8.8 from `tests/test_pipeline_e2e.py`
- Test cases 9.1-9.5 for logging verification
- Verify response metadata completeness (request_id, input_mode, api_calls, etc.)

## Test: `tests/test_anti_overfit.py`

Test cases 6.1-6.10 from `tests/test_anti_overfit.py`. These queries are NOT in the examples.

If any requires a code change, the system is overfit.
