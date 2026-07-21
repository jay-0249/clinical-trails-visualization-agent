"""Phase 10 — end-to-end via FastAPI TestClient. Integration only (real API + LLM).

Deselected from the hermetic suite; run with `pytest -m integration`.
One rich primary POST drives the metadata (8.8), logging (9.x), and viz-spec
(10.x) checks; a few extra POSTs cover comparison, network, and errors.
"""

import io
import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.utils.logger import StructuredFormatter

_LOGGERS = ["orchestrator", "ct_client", "query_analyzer", "viz_generator", "main"]


@pytest.fixture(scope="module")
def client():
    settings.ct_api_page_size = 60  # small pages keep the e2e payloads light
    with TestClient(app) as c:  # entering the context runs lifespan -> loads cache
        yield c


def _capture():
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(StructuredFormatter())
    for name in _LOGGERS:
        logging.getLogger(name).addHandler(handler)
    return buf, handler


def _detach(handler):
    for name in _LOGGERS:
        logging.getLogger(name).removeHandler(handler)


@pytest.fixture(scope="module")
def primary(client):
    """One POST that exercises citations, a param filter, metadata, logging, viz."""
    buf, handler = _capture()
    resp = client.post(
        "/api/v1/query",
        json={
            "query": "How are Pembrolizumab trials distributed across phases?",
            "drug_name": "Pembrolizumab",
            "include_citations": True,
            "max_studies": 60,
        },
    )
    _detach(handler)
    assert resp.status_code == 200, resp.text
    logs = [json.loads(line) for line in buf.getvalue().splitlines() if line.strip()]
    return resp.json(), logs


# --- 8.1 / 8.6 / 8.7 ------------------------------------------------------


@pytest.mark.integration
def test_8_1_categorical_phase_counts(primary):
    data, _ = primary
    v = data["visualizations"][0]
    assert v["type_category"] == "categorical"
    assert v["data"] and all("value" in row for row in v["data"])


@pytest.mark.integration
def test_8_6_citations_per_group(primary):
    data, _ = primary
    v = data["visualizations"][0]
    cited = [r for r in v["data"] if r.get("citations")]
    assert cited
    assert "nct_id" in cited[0]["citations"][0]


@pytest.mark.integration
def test_8_7_filters_applied_and_interpretation(primary):
    data, _ = primary
    m = data["meta"]
    assert "query.intr" in m["filters_applied"]
    assert m["input_interpretation"]["from_params"].get("drug_name") == "Pembrolizumab"


# --- 8.8 metadata completeness (the most important) -----------------------


@pytest.mark.integration
def test_8_8_metadata_completeness(primary):
    data, _ = primary
    m = data["meta"]
    uuid.UUID(m["request_id"])  # raises if not a valid UUID
    assert m["original_query"]
    assert m["input_mode"] == "supplement"
    interp = m["input_interpretation"]
    for k in ("from_query", "from_params", "conflicts", "resolution"):
        assert k in interp
    assert isinstance(m["filters_applied"], dict)
    assert m["total_studies_analyzed"] > 0
    assert m["api_calls"]
    call = m["api_calls"][0]
    for k in ("endpoint", "params", "http_status", "record_count", "duration_ms"):
        assert k in call
    assert m["stage_timings"]
    assert m["api_version"] and m["data_refresh"]
    assert m["source"] == "clinicaltrials.gov"


# --- 9.x logging ----------------------------------------------------------


@pytest.mark.integration
def test_9_1_9_2_events_and_single_request_id(primary):
    _, logs = primary
    events = {entry.get("event") for entry in logs}
    for e in (
        "pipeline_start",
        "stage_start",
        "stage_complete",
        "api_call",
        "llm_call",
        "pipeline_complete",
    ):
        assert e in events, f"missing log event: {e}"
    rids = {entry.get("request_id") for entry in logs if entry.get("request_id")}
    assert len(rids) == 1  # all pipeline logs share one request_id


@pytest.mark.integration
def test_9_3_api_calls_logged(primary):
    _, logs = primary
    api = [entry for entry in logs if entry.get("event") == "api_call"]
    assert api
    for k in ("endpoint", "http_status", "record_count", "duration_ms"):
        assert k in api[0]


@pytest.mark.integration
def test_9_4_llm_calls_logged(primary):
    _, logs = primary
    llm = [entry for entry in logs if entry.get("event") == "llm_call"]
    assert llm
    assert any(e.get("model") and e.get("output_valid") is True for e in llm)
    assert any("prompt_tokens" in e or "completion_tokens" in e for e in llm)


# --- 10.x viz spec contract -----------------------------------------------


@pytest.mark.integration
def test_10_viz_spec_contract(primary):
    data, _ = primary
    v = data["visualizations"][0]
    enc = v["encoding"]
    assert "category" in enc and "value" in enc  # categorical contract
    cols = set().union(*[set(r.keys()) for r in v["data"]])
    assert enc["category"]["field"] in cols  # field names exist in data
    assert enc["value"]["field"] in cols
    assert v["type"] and v["type"] not in ("chart", "")  # specific type
    assert v["title"] and v["title"].lower() != "chart"
    assert v["rendering_hints"].get("color_scheme")


# --- 8.3 comparison / 8.4 network / 9.5 validation failure ----------------


@pytest.mark.integration
def test_8_3_comparison_entity_tags(client):
    resp = client.post(
        "/api/v1/query",
        json={"query": "Compare Pembrolizumab vs Nivolumab by phase", "max_studies": 60},
    )
    assert resp.status_code == 200, resp.text
    m = resp.json()["meta"]
    assert m["query_complexity"] == "comparative"
    assert len(m["input_interpretation"]["from_query"]) >= 2  # two data requirements


@pytest.mark.integration
def test_8_4_network_relational(client):
    resp = client.post(
        "/api/v1/query",
        json={"query": "Sponsor-drug network for breast cancer", "max_studies": 60},
    )
    assert resp.status_code == 200, resp.text
    v = resp.json()["visualizations"][0]
    assert v["type_category"] == "relational"
    for k in ("source", "target", "weight"):
        assert k in v["encoding"]


@pytest.mark.integration
def test_9_5_validation_failure_surfaces_valid_values(client):
    resp = client.post(
        "/api/v1/query", json={"query": "trials by phase", "trial_phase": "PHASE99"}
    )
    assert resp.status_code == 400
    assert "valid_values" in resp.json()["detail"]


@pytest.mark.integration
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["cache_loaded"] is True
    assert body["api_version"]
