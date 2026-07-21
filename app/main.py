"""FastAPI app: startup reference-cache load + the single query endpoint.

A fresh CTGovClient is created per request (it accumulates that request's API
calls for the response metadata — no cross-request state). Pipeline exceptions
are mapped to structured ErrorResponse bodies with appropriate HTTP status.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.pipeline.aggregator import AggregationError
from app.pipeline.orchestrator import build_error_response, execute
from app.pipeline.query_analyzer import QueryAnalysisError
from app.pipeline.viz_generator import VizGenerationError
from app.schemas.request import QueryRequest
from app.schemas.response import PipelineResponse
from app.services.ct_client import CTGovClient
from app.services.reference_cache import ReferenceDataCache
from app.utils.logger import get_logger, log_event
from app.utils.validators import IntentValidationError

logger = get_logger("main")
reference_cache = ReferenceDataCache(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await reference_cache.load()
    log_event(
        logger,
        logging.INFO,
        "startup",
        api_version=reference_cache.api_version,
        cache_loaded=reference_cache.loaded,
    )
    yield


app = FastAPI(
    title="ClinicalTrials.gov Query-to-Visualization Agent",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "api_version": reference_cache.api_version,
        "cache_loaded": reference_cache.loaded,
        "data_refresh": reference_cache.last_refresh,
    }


@app.post("/api/v1/query", response_model=PipelineResponse)
async def query(request: QueryRequest):
    ct_client = CTGovClient(settings)
    try:
        return await execute(request, reference_cache, ct_client)
    except HTTPException as exc:
        # Pre-LLM structured-hint validation (invalid enum) — 400 with valid values.
        if isinstance(exc.detail, dict):
            log_event(
                logger,
                logging.WARNING,
                "validation_failure",
                error=exc.detail.get("error"),
                valid_values=exc.detail.get("valid_values"),
            )
        raise
    except IntentValidationError as exc:
        log_event(logger, logging.WARNING, "validation_failure", error=str(exc)[:200])
        raise HTTPException(status_code=422, detail=build_error_response(exc).model_dump())
    except (QueryAnalysisError, AggregationError, VizGenerationError) as exc:
        log_event(logger, logging.ERROR, "pipeline_error", error_type=type(exc).__name__)
        raise HTTPException(status_code=500, detail=build_error_response(exc).model_dump())
    except Exception as exc:  # noqa: BLE001 - last-resort structured 500
        log_event(logger, logging.ERROR, "pipeline_error", error_type=type(exc).__name__)
        raise HTTPException(status_code=500, detail=build_error_response(exc).model_dump())
