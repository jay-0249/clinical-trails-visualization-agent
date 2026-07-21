"""Phase 6 aggregator tests (cases 4.1-4.16) — the most important test file.

Pure fixtures, no API or LLM. Verifies all 3 output modes plus the anti-overfit
guarantee (a field never used in the examples still works).
"""

from app.pipeline.aggregator import aggregate
from app.schemas.intent import AggregationSpec
from app.schemas.trial_record import StudyRecord


def make_study(nct="NCT1", **kw) -> StudyRecord:
    base = dict(
        nct_id=nct,
        title="t",
        status="RECRUITING",
        phases=["PHASE1"],
        phase_label="Phase 1",
        conditions=["C1"],
        interventions=["I1"],
        intervention_types=["DRUG"],
        sponsor_name="S",
        sponsor_class="INDUSTRY",
        start_year=2015,
        start_month=1,
        completion_year=2018,
        countries=["US"],
        cities=["Boston"],
        enrollment=100,
        study_type="INTERVENTIONAL",
        excerpt="ex",
        source_query="q",
    )
    base.update(kw)
    return StudyRecord(**base)


def spec(**kw) -> AggregationSpec:
    base = dict(group_by=["phase_label"], metric="count")
    base.update(kw)
    return AggregationSpec(**base)


# --- Aggregated mode ------------------------------------------------------


def test_4_1_single_field_count():
    labels = ["Phase 1"] * 5 + ["Phase 2"] * 3 + ["Phase 3"] * 2
    recs = [make_study(nct=f"N{i}", phase_label=p) for i, p in enumerate(labels)]
    out = aggregate(recs, spec(group_by=["phase_label"], metric="count"))
    assert sum(r["value"] for r in out) == 10
    assert len(out) == 3
    assert {r["phase_label"]: r["value"] for r in out} == {
        "Phase 1": 5,
        "Phase 2": 3,
        "Phase 3": 2,
    }


def test_4_2_multi_field_count():
    recs = [
        make_study(nct="a", phase_label="Phase 1", sponsor_class="INDUSTRY"),
        make_study(nct="b", phase_label="Phase 1", sponsor_class="INDUSTRY"),
        make_study(nct="c", phase_label="Phase 1", sponsor_class="NIH"),
        make_study(nct="d", phase_label="Phase 2", sponsor_class="NIH"),
    ]
    out = aggregate(recs, spec(group_by=["phase_label", "sponsor_class"]))
    pairs = {(r["phase_label"], r["sponsor_class"]): r["value"] for r in out}
    assert len(out) == 3
    assert pairs[("Phase 1", "INDUSTRY")] == 2
    assert pairs[("Phase 1", "NIH")] == 1
    assert pairs[("Phase 2", "NIH")] == 1


def test_4_3_list_field_explosion():
    recs = [
        make_study(nct="a", countries=["US", "UK"]),
        make_study(nct="b", countries=["US"]),
        make_study(nct="c", countries=["UK", "France"]),
    ]
    out = aggregate(recs, spec(group_by=["countries"]))
    assert {r["countries"]: r["value"] for r in out} == {"US": 2, "UK": 2, "France": 1}


def test_4_4_sum_metric():
    recs = [
        make_study(nct="a", phase_label="P1", enrollment=100),
        make_study(nct="b", phase_label="P1", enrollment=50),
        make_study(nct="c", phase_label="P2", enrollment=200),
    ]
    out = aggregate(recs, spec(metric="sum", metric_field="enrollment"))
    assert {r["phase_label"]: r["value"] for r in out} == {"P1": 150, "P2": 200}


def test_4_5_unique_count_metric():
    recs = [
        make_study(nct="a", phase_label="P1", conditions=["X", "Y"]),
        make_study(nct="b", phase_label="P1", conditions=["Y", "Z"]),
        make_study(nct="c", phase_label="P2", conditions=["X"]),
    ]
    out = aggregate(recs, spec(metric="unique_count", metric_field="conditions"))
    assert {r["phase_label"]: r["value"] for r in out} == {"P1": 3, "P2": 1}


def test_4_6_time_granularity_year_sorted():
    recs = [
        make_study(nct="a", start_year=2018),
        make_study(nct="b", start_year=2015),
        make_study(nct="c", start_year=2016),
        make_study(nct="d", start_year=2015),
    ]
    out = aggregate(recs, spec(group_by=["start_year"], time_granularity="year"))
    years = [r["start_year"] for r in out]
    assert years == [2015, 2016, 2018]
    assert {r["start_year"]: r["value"] for r in out}[2015] == 2


def test_4_7_sort_descending():
    labels = ["A"] * 1 + ["B"] * 3 + ["C"] * 2
    recs = [make_study(nct=f"N{i}", phase_label=p) for i, p in enumerate(labels)]
    out = aggregate(recs, spec(group_by=["phase_label"], sort_by="value_desc"))
    assert [r["value"] for r in out] == [3, 2, 1]


def test_4_8_null_group_field():
    recs = [
        make_study(nct="a", sponsor_class="INDUSTRY"),
        make_study(nct="b", sponsor_class=None),
        make_study(nct="c", sponsor_class=None),
    ]
    out = aggregate(recs, spec(group_by=["sponsor_class"]))
    d = {r["sponsor_class"]: r["value"] for r in out}
    assert d["Unknown"] == 2
    assert d["INDUSTRY"] == 1


def test_4_9_empty_records():
    assert aggregate([], spec()) == []


def test_4_10_citations_capped():
    recs = [make_study(nct=f"N{i}", phase_label="P1", excerpt=f"ex{i}") for i in range(4)]
    recs.append(make_study(nct="X", phase_label="P2"))
    out = aggregate(recs, spec(), include_citations=True, max_citations_per_group=2)
    p1 = next(r for r in out if r["phase_label"] == "P1")
    assert p1["value"] == 4  # value still counts all members
    assert len(p1["citations"]) == 2
    assert all("nct_id" in c and "excerpt" in c for c in p1["citations"])


# --- Raw records mode -----------------------------------------------------


def test_4_11_raw_records():
    recs = [make_study(nct="a", enrollment=100), make_study(nct="b", enrollment=200)]
    out = aggregate(
        recs, spec(group_by=[], metric_field="enrollment", output_mode="raw_records")
    )
    assert {(r["value"], r["nct_id"]) for r in out} == {(100, "a"), (200, "b")}


def test_4_12_raw_records_null_excluded():
    recs = [make_study(nct="a", enrollment=100), make_study(nct="b", enrollment=None)]
    out = aggregate(
        recs, spec(group_by=[], metric_field="enrollment", output_mode="raw_records")
    )
    assert out == [{"value": 100, "nct_id": "a"}]


def test_raw_records_scatter_extra_axes():
    recs = [make_study(nct="a", enrollment=100, start_year=2015)]
    out = aggregate(
        recs,
        spec(
            group_by=["start_year"],
            metric_field="enrollment",
            output_mode="raw_records",
        ),
    )
    assert out == [{"value": 100, "nct_id": "a", "start_year": 2015}]


# --- Edge list mode -------------------------------------------------------


def test_4_13_edge_list_cooccurrence():
    recs = [
        make_study(nct="a", sponsor_name="Pfizer", interventions=["A", "B"]),
        make_study(nct="b", sponsor_name="Merck", interventions=["A"]),
    ]
    out = aggregate(
        recs,
        spec(group_by=["sponsor_name", "interventions"], output_mode="edge_list"),
    )
    edges = {(e["source"], e["target"]): e["weight"] for e in out}
    assert edges == {("Pfizer", "A"): 1, ("Pfizer", "B"): 1, ("Merck", "A"): 1}


def test_4_14_edge_list_from_list_field():
    recs = [make_study(nct="a", sponsor_name="Pfizer", interventions=["A", "B", "C"])]
    out = aggregate(
        recs,
        spec(group_by=["sponsor_name", "interventions"], output_mode="edge_list"),
    )
    assert len(out) == 3
    assert all(e["source"] == "Pfizer" and e["weight"] == 1 for e in out)


def test_4_15_edge_weight_accumulation():
    recs = [
        make_study(nct=f"N{i}", sponsor_name="Pfizer", interventions=["DrugX"])
        for i in range(3)
    ]
    out = aggregate(
        recs,
        spec(group_by=["sponsor_name", "interventions"], output_mode="edge_list"),
    )
    assert len(out) == 1
    assert out[0] == {"source": "Pfizer", "target": "DrugX", "weight": 3}


def test_edge_list_citations():
    recs = [
        make_study(nct="a", sponsor_name="P", interventions=["X"]),
        make_study(nct="b", sponsor_name="P", interventions=["X"]),
    ]
    out = aggregate(
        recs,
        spec(group_by=["sponsor_name", "interventions"], output_mode="edge_list"),
        include_citations=True,
    )
    assert out[0]["citations"] == ["a", "b"]


# --- 4.16 anti-overfit: a field never used above --------------------------


def test_4_16_field_not_in_examples():
    recs = [
        make_study(nct="a", study_type="INTERVENTIONAL"),
        make_study(nct="b", study_type="OBSERVATIONAL"),
        make_study(nct="c", study_type="INTERVENTIONAL"),
    ]
    out = aggregate(recs, spec(group_by=["study_type"]))
    assert {r["study_type"]: r["value"] for r in out} == {
        "INTERVENTIONAL": 2,
        "OBSERVATIONAL": 1,
    }
