"""Phase 8 — Stage 4 viz generator. Integration-only (real OpenAI calls).

Deselected from the hermetic suite; run with `pytest -m integration -s`.
Feeds 5 data shapes and checks the LLM picks the right type_category, the
encoding follows the contract, and the data is injected verbatim.
"""

import pytest

from app.pipeline.viz_generator import _normalize_encoding, _verify_encoding, generate
from app.schemas.intent import AggregationSpec, AnalysisTask
from app.schemas.response import VisualizationSpec


# --- hermetic: encoding key normalization (Bug 2 fix) ---------------------


def test_normalize_encoding_spatial_synonym():
    spec = VisualizationSpec(
        task_id="t",
        description="d",
        type="choropleth",
        type_category="spatial",
        title="Trials by Country",
        encoding={"country": {"field": "countries"}, "value": {"field": "value"}},
        data=[],
    )
    _normalize_encoding(spec)
    assert "location" in spec.encoding and "country" not in spec.encoding
    assert spec.encoding["location"]["field"] == "countries"
    _verify_encoding(spec, [{"countries": "US", "value": 3}])  # now passes the contract


def test_normalize_encoding_relational_synonyms():
    spec = VisualizationSpec(
        task_id="t",
        description="d",
        type="network",
        type_category="relational",
        title="Network",
        encoding={
            "from": {"field": "source"},
            "to": {"field": "target"},
            "weight": {"field": "weight"},
        },
        data=[],
    )
    _normalize_encoding(spec)
    assert {"source", "target", "weight"} <= set(spec.encoding)


def make_task(categories, description, task_id="t1"):
    # aggregation is not used by generate(); a minimal valid one keeps the model happy.
    return AnalysisTask(
        task_id=task_id,
        description=description,
        aggregation=AggregationSpec(group_by=["phase_label"], metric="count"),
        candidate_viz_categories=categories,
    )


def _common_checks(spec: VisualizationSpec, data, expected_category):
    assert spec.type_category == expected_category
    assert isinstance(spec.type, str) and spec.type  # open string, non-empty
    assert spec.title and spec.title.lower() not in ("bar chart", "data visualization")
    assert spec.data == data  # injected verbatim, never invented
    assert spec.rendering_hints  # at least something (color_scheme etc.)
    _verify_encoding(spec, data)  # contract + real columns (also done inside generate)


@pytest.mark.integration
async def test_categorical_shape():
    data = [
        {"phase_label": "Phase 1", "value": 32},
        {"phase_label": "Phase 2", "value": 78},
        {"phase_label": "Phase 3", "value": 41},
    ]
    spec = await generate(
        make_task(["categorical"], "Distribution of trials across phases"),
        data,
        "How are Pembrolizumab trials distributed across phases?",
    )
    print("\n[categorical]", spec.type, spec.type_category, "|", spec.encoding)
    _common_checks(spec, data, "categorical")


@pytest.mark.integration
async def test_temporal_shape():
    data = [
        {"start_year": 2015, "value": 5},
        {"start_year": 2016, "value": 9},
        {"start_year": 2017, "value": 14},
        {"start_year": 2018, "value": 20},
    ]
    spec = await generate(
        make_task(["temporal"], "Number of trials started per year"),
        data,
        "How has the number of trials changed per year?",
    )
    print("\n[temporal]", spec.type, spec.type_category, "|", spec.encoding)
    _common_checks(spec, data, "temporal")


@pytest.mark.integration
async def test_relational_shape():
    data = [
        {"source": "Pfizer", "target": "DrugA", "weight": 12},
        {"source": "Merck", "target": "DrugA", "weight": 7},
        {"source": "Pfizer", "target": "DrugB", "weight": 3},
    ]
    spec = await generate(
        make_task(["relational"], "Network of sponsors and drugs"),
        data,
        "Show a network of sponsors and drugs for breast cancer trials",
    )
    print("\n[relational]", spec.type, spec.type_category, "|", spec.encoding)
    _common_checks(spec, data, "relational")


@pytest.mark.integration
async def test_matrix_shape_picks_heatmap_not_bar():
    # Two categorical dims, each >4 unique values -> matrix should win over categorical.
    data = [
        {"start_year": y, "sponsor_class": c, "value": (y % 5) + 1}
        for y in range(2015, 2021)
        for c in ["INDUSTRY", "NIH", "FED", "OTHER", "NETWORK"]
    ]
    spec = await generate(
        make_task(["matrix", "categorical"], "Sponsor class by start year"),
        data,
        "How have sponsor types changed over time?",
    )
    print("\n[matrix]", spec.type, spec.type_category, "|", spec.encoding)
    _common_checks(spec, data, "matrix")


@pytest.mark.integration
async def test_distribution_shape():
    data = [{"value": v, "nct_id": f"NCT{v}"} for v in [50, 120, 80, 200, 45, 300, 95]]
    spec = await generate(
        make_task(["distribution"], "Enrollment distribution"),
        data,
        "What's the enrollment distribution across Phase 3 trials?",
    )
    print("\n[distribution]", spec.type, spec.type_category, "|", spec.encoding)
    _common_checks(spec, data, "distribution")
