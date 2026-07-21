# Phase 2: Utilities

**Files to create:**

- `app/utils/date_parser.py`
- `app/utils/logger.py` (addition to base structure)
- `app/config.py`

---

## date_parser.py

The ClinicalTrials.gov API returns dates in inconsistent formats. Write a single function that handles all of them.

```python
def parse_date(value) -> tuple[int | None, int | None]:
    """Parse messy CT.gov dates into (year, month).

    Handles:
    - "2024-01-15" (ISO date)
    - "January 2024" (month year)
    - "January 15, 2024" (full date string)
    - "2024-01" (year-month)
    - "2024" (year only)
    - {"date": "2024-01-15", "type": "ACTUAL"} (date struct from API)
    - None, empty string, malformed -> (None, None)
    """
```

Implementation notes:

- If input is a dict, extract the `date` field and re-parse
- Try ISO parsing first (fastest), then regex for text formats
- Never crash — always return `(None, None)` for unrecognizable input

## logger.py

Structured JSON logging with request_id tracking.

```python
import logging
import json
from datetime import datetime, timezone
from contextlib import contextmanager
import time

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
        log_event(logger, logging.INFO, "stage_complete",
            request_id=ctx.request_id, stage=stage_name, duration_ms=duration_ms)
```

## config.py

```python
from pydantic_settings import BaseSettings
# or use python-dotenv if pydantic-settings not available

class Settings(BaseSettings):
    llm_api_key: str
    llm_model: str = "gpt-4o"
    llm_provider: str = "openai"
    ct_api_base_url: str = "https://clinicaltrials.gov/api/v2"
    ct_api_page_size: int = 1000
    ct_api_max_pages: int = 10
    ct_api_timeout_seconds: int = 30
    ct_api_rate_limit_delay: float = 1.2
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
```

Also create a `safe_get` utility (can go in `date_parser.py` or a separate helpers file):

```python
def safe_get(data: dict, path: str, default=None):
    keys = path.split('.')
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data if data is not None else default
```

---

## Test: `tests/test_date_parser.py`
