"""Phase 2 utility tests: date_parser cases 1.1-1.9, plus logger, config, safe_get."""

import io
import json
import logging

import pytest

from app.config import Settings
from app.schemas.trial_record import PipelineContext
from app.utils.date_parser import parse_date
from app.utils.helpers import safe_get
from app.utils.logger import StructuredFormatter, get_logger, log_event, timed_stage


# --- date_parser: cases 1.1 - 1.9 ----------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2024-01-15", (2024, 1)),  # 1.1 ISO date
        ("January 2024", (2024, 1)),  # 1.2 month year
        ("January 15, 2024", (2024, 1)),  # 1.3 full date string
        ("2024-01", (2024, 1)),  # 1.4 year-month
        ({"date": "2024-01-15", "type": "ACTUAL"}, (2024, 1)),  # 1.5 date struct
        ("2024", (2024, None)),  # 1.6 year only
        (None, (None, None)),  # 1.7 None
        ("", (None, None)),  # 1.8 empty string
        ("not-a-date", (None, None)),  # 1.9 malformed, no crash
    ],
)
def test_parse_date_cases(value, expected):
    assert parse_date(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Jan 2024", (2024, 1)),  # abbreviated month
        ("Sep 2019", (2019, 9)),
        ("2024-13", (2024, None)),  # invalid month -> dropped
        ({"date": None}, (None, None)),  # struct with null date
        ({}, (None, None)),  # empty struct
        (2024, (None, None)),  # non-str, non-dict -> no crash
        ("   2020-06-01  ", (2020, 6)),  # surrounding whitespace
    ],
)
def test_parse_date_extra(value, expected):
    assert parse_date(value) == expected


# --- safe_get -------------------------------------------------------------


def test_safe_get_nested_and_missing():
    d = {"a": {"b": {"c": 5}}}
    assert safe_get(d, "a.b.c") == 5
    assert safe_get(d, "a.b") == {"c": 5}
    assert safe_get(d, "a.x.c", "default") == "default"
    assert safe_get(d, "a.b.c.d", 0) == 0  # descend past a scalar -> default
    assert safe_get({}, "a", None) is None


# --- logger ---------------------------------------------------------------


def test_logger_emits_json_with_request_id():
    logger = logging.getLogger("test_capture")
    logger.handlers.clear()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(StructuredFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_event(logger, logging.INFO, "stage_start", request_id="req-9", stage="s1")

    entry = json.loads(buf.getvalue().strip())
    assert entry["event"] == "stage_start"
    assert entry["request_id"] == "req-9"
    assert entry["stage"] == "s1"
    assert entry["level"] == "INFO"
    assert "timestamp" in entry


def test_timed_stage_records_duration():
    ctx = PipelineContext(request_id="req-10")
    logger = get_logger("test_timed")
    with timed_stage(logger, ctx, "stage_x"):
        pass
    assert "stage_x" in ctx.stage_timings
    assert ctx.stage_timings["stage_x"] >= 0


# --- config ---------------------------------------------------------------


def test_config_loads_defaults():
    s = Settings(_env_file=None)
    assert s.llm_model_main == "gpt-4o"
    assert s.llm_model_subagent == "gpt-4o-mini"
    assert s.ct_api_base_url == "https://clinicaltrials.gov/api/v2"
    assert s.ct_api_page_size == 1000
    assert s.ct_api_max_pages == 10
    assert s.ct_api_timeout_seconds == 30
    assert s.max_studies == 5000
