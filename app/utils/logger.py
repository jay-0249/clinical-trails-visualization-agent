"""Structured JSON logging with request_id propagation.

Every log line is one JSON object carrying timestamp, level, event,
request_id, and any event-specific fields. `timed_stage` records per-stage
durations into the PipelineContext for the response metadata.
"""

import json
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "event": getattr(record, "event", record.msg),
            "request_id": getattr(record, "request_id", None),
        }
        if hasattr(record, "extra_fields"):
            entry.update(record.extra_fields)
        return json.dumps(entry)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # don't double-log through the root handler
    return logger


def log_event(logger, level, event, request_id=None, **kwargs):
    record = logger.makeRecord(logger.name, level, "", 0, event, (), None)
    record.event = event
    record.request_id = request_id
    record.extra_fields = kwargs
    logger.handle(record)


@contextmanager
def timed_stage(logger, ctx, stage_name):
    start = time.perf_counter()
    log_event(logger, logging.INFO, "stage_start", request_id=ctx.request_id, stage=stage_name)
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        ctx.stage_timings[stage_name] = duration_ms
        log_event(
            logger,
            logging.INFO,
            "stage_complete",
            request_id=ctx.request_id,
            stage=stage_name,
            duration_ms=duration_ms,
        )
