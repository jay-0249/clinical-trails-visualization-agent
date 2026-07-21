"""Phase 11 — anti-overfit gate (cases 6.1-6.10) + error handling (7.1-7.3).

Integration only (real API + LLM). Each query must be HANDLED without a code
change: a 200 with a valid visualization, or a handled 4xx structured error.
Run with `pytest tests/test_anti_overfit.py -m integration -v`.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

_VALID_CATEGORIES = {
    "categorical",
    "temporal",
    "relational",
    "spatial",
    "matrix",
    "hierarchical",
    "distribution",
}


@pytest.fixture(scope="module")
def client():
    settings.ct_api_page_size = 25  # tiny pages — coverage, not completeness
    with TestClient(app) as c:  # lifespan loads the reference cache
        yield c


# --- 6.1-6.10 anti-overfit queries ----------------------------------------

_STRICT = [
    ("6.1", {"query": "How are Trastuzumab trials distributed across phases?"}),
    ("6.2", {"query": "Show trial trends for Crohn's disease since 2010"}),
    ("6.3", {"query": "Enrollment distribution for Phase 3 cancer trials"}),
    ("6.4", {"query": "Sponsor types over time for diabetes"}),
    ("6.5", {"query": "Break down breast cancer trials by sponsor type, then sponsor, then drug"}),
    ("6.6", {"query": "Countries with most recruiting HIV trials"}),
    ("6.7", {"query": "Which drugs co-occur in lymphoma combination studies?"}),
    ("6.8", {"query": "Show Phase 3 Pembrolizumab trials by phase and their geographic distribution"}),
    ("6.10", {"query": "Most common study types for Alzheimer's trials"}),
]


@pytest.mark.integration
@pytest.mark.parametrize("case,payload", _STRICT, ids=[c for c, _ in _STRICT])
def test_anti_overfit_query_produces_viz(client, case, payload):
    resp = client.post("/api/v1/query", json={**payload, "max_studies": 25})
    assert resp.status_code == 200, f"{case}: {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body["visualizations"], f"{case}: no visualizations"
    for v in body["visualizations"]:
        assert v["type_category"] in _VALID_CATEGORIES, f"{case}: {v['type_category']}"
        assert isinstance(v["data"], list)
    # request_id + timings present -> the full pipeline ran generically
    assert body["meta"]["request_id"] and body["meta"]["stage_timings"]


@pytest.mark.integration
def test_6_9_vague_override_is_handled(client):
    # Deliberately underspecified: a valid default viz OR a handled 422 is fine —
    # both mean the system coped without a code change.
    resp = client.post(
        "/api/v1/query",
        json={"query": "show me", "drug_name": "Pembrolizumab", "input_mode": "override", "max_studies": 25},
    )
    assert resp.status_code in (200, 422), f"{resp.status_code} {resp.text[:300]}"
    if resp.status_code == 200:
        assert resp.json()["visualizations"]
    else:
        assert "detail" in resp.json()  # structured, not a crash


# --- 7.1-7.3 error handling ------------------------------------------------


@pytest.mark.integration
def test_7_1_zero_results_nonexistent_drug(client):
    resp = client.post(
        "/api/v1/query",
        json={"query": "Phase distribution for Zzqxdrugnotreal trials", "max_studies": 25},
    )
    # Zero results is valid: 200 with an (empty) viz, or a handled error.
    assert resp.status_code in (200, 422), resp.text[:300]
    if resp.status_code == 200:
        assert "visualizations" in resp.json()


@pytest.mark.integration
def test_7_2_query_too_short(client):
    resp = client.post("/api/v1/query", json={"query": "hi"})
    assert resp.status_code == 422  # request-body validation (min_length=3)


@pytest.mark.integration
def test_7_3_invalid_enum(client):
    resp = client.post(
        "/api/v1/query", json={"query": "trials by phase", "trial_phase": "PHASE99"}
    )
    assert resp.status_code == 400
    assert "valid_values" in resp.json()["detail"]
