"""Phase 3 tests: normalization (2.1-2.10), phase_label, live smoke (2.11)."""

import pytest

from app.config import Settings
from app.schemas.intent import DataRequirement
from app.schemas.trial_record import StudyRecord
from app.services.ct_client import CTGovClient, normalize_study, phase_label


# --- fixture builders -----------------------------------------------------


def wrap(**modules) -> dict:
    """Wrap protocolSection modules into a raw study dict."""
    return {"protocolSection": modules}


def complete_raw() -> dict:
    return wrap(
        identificationModule={"nctId": "NCT01234567", "briefTitle": "A Complete Study"},
        statusModule={
            "overallStatus": "RECRUITING",
            "startDateStruct": {"date": "2018-03-01", "type": "ACTUAL"},
            "completionDateStruct": {"date": "2021-12", "type": "ESTIMATED"},
        },
        designModule={
            "phases": ["PHASE2", "PHASE3"],
            "studyType": "INTERVENTIONAL",
            "enrollmentInfo": {"count": 150, "type": "ACTUAL"},
        },
        conditionsModule={"conditions": ["Melanoma", "Lung Cancer"]},
        armsInterventionsModule={
            "interventions": [
                {"type": "DRUG", "name": "DrugA"},
                {"type": "DRUG", "name": "DrugB"},
                {"type": "BIOLOGICAL", "name": "VaccineC"},
            ]
        },
        sponsorCollaboratorsModule={
            "leadSponsor": {"name": "Acme Research", "class": "INDUSTRY"}
        },
        contactsLocationsModule={
            "locations": [
                {"facility": "F1", "city": "Boston", "country": "United States"},
                {"facility": "F2", "city": "Berlin", "country": "Germany"},
                {"facility": "F3", "city": "Boston", "country": "United States"},
            ]
        },
        descriptionModule={"briefSummary": "A study of DrugA and DrugB."},
    )


# --- 2.1 complete ---------------------------------------------------------


def test_2_1_complete_record():
    s = normalize_study(complete_raw(), source_query="r1")
    assert s.nct_id == "NCT01234567"
    assert s.title == "A Complete Study"
    assert s.status == "RECRUITING"
    assert s.phases == ["PHASE2", "PHASE3"]
    assert s.phase_label == "Phase 2/Phase 3"
    assert s.conditions == ["Melanoma", "Lung Cancer"]
    assert s.interventions == ["DrugA", "DrugB", "VaccineC"]
    assert s.intervention_types == ["DRUG", "DRUG", "BIOLOGICAL"]
    assert s.sponsor_name == "Acme Research"
    assert s.sponsor_class == "INDUSTRY"
    assert (s.start_year, s.start_month) == (2018, 3)
    assert s.completion_year == 2021
    assert s.countries == ["United States", "Germany"]
    assert s.cities == ["Boston", "Berlin"]
    assert s.enrollment == 150
    assert s.study_type == "INTERVENTIONAL"
    assert s.excerpt == "A study of DrugA and DrugB."
    assert s.source_query == "r1"


# --- 2.2 minimal ----------------------------------------------------------


def test_2_2_minimal_record_no_crash():
    s = normalize_study(
        wrap(identificationModule={"nctId": "NCT9", "briefTitle": "Bare"})
    )
    assert s.nct_id == "NCT9"
    assert s.title == "Bare"
    assert s.status == ""
    assert s.phases == [] and s.phase_label == "N/A"
    assert s.conditions == [] and s.interventions == [] and s.intervention_types == []
    assert s.sponsor_name is None and s.sponsor_class is None
    assert s.start_year is None and s.completion_year is None
    assert s.countries == [] and s.cities == []
    assert s.enrollment is None and s.study_type is None
    assert s.excerpt == ""


# --- 2.3-2.5 phase_label via normalization --------------------------------


def test_2_3_multi_phase():
    s = normalize_study(wrap(designModule={"phases": ["PHASE1", "PHASE2"]}))
    assert s.phase_label == "Phase 1/Phase 2"


def test_2_4_single_phase():
    s = normalize_study(wrap(designModule={"phases": ["PHASE3"]}))
    assert s.phase_label == "Phase 3"


def test_2_5_no_phase():
    assert normalize_study(wrap(designModule={"phases": []})).phase_label == "N/A"
    assert normalize_study(wrap(designModule={"phases": None})).phase_label == "N/A"
    assert normalize_study(wrap(designModule={})).phase_label == "N/A"


def test_phase_label_all_scenarios():
    assert phase_label([]) == "N/A"
    assert phase_label(["PHASE4"]) == "Phase 4"
    assert phase_label(["EARLY_PHASE1"]) == "Early Phase 1"
    assert phase_label(["NA"]) == "N/A"
    assert phase_label(["PHASE1", "PHASE2", "PHASE3"]) == "Phase 1/Phase 2/Phase 3"


# --- 2.6-2.7 locations ----------------------------------------------------


def test_2_6_unique_countries():
    s = normalize_study(
        wrap(
            contactsLocationsModule={
                "locations": [
                    {"city": "Boston", "country": "United States"},
                    {"city": "Berlin", "country": "Germany"},
                    {"city": "Chicago", "country": "United States"},
                ]
            }
        )
    )
    assert s.countries == ["United States", "Germany"]
    assert s.cities == ["Boston", "Berlin", "Chicago"]


def test_2_7_null_locations():
    s = normalize_study(wrap(contactsLocationsModule={"locations": None}))
    assert s.countries == [] and s.cities == []


# --- 2.8 interventions ----------------------------------------------------


def test_2_8_interventions():
    s = normalize_study(
        wrap(
            armsInterventionsModule={
                "interventions": [
                    {"type": "DRUG", "name": "X"},
                    {"type": "DEVICE", "name": "Y"},
                    {"type": "PROCEDURE", "name": "Z"},
                ]
            }
        )
    )
    assert s.interventions == ["X", "Y", "Z"]
    assert s.intervention_types == ["DRUG", "DEVICE", "PROCEDURE"]


# --- 2.9-2.10 enrollment --------------------------------------------------


def test_2_9_enrollment_present():
    s = normalize_study(wrap(designModule={"enrollmentInfo": {"count": 150}}))
    assert s.enrollment == 150


def test_2_10_enrollment_null():
    assert normalize_study(wrap(designModule={"enrollmentInfo": None})).enrollment is None
    assert normalize_study(wrap(designModule={})).enrollment is None


# --- 2.11 live smoke (deselected by default; run with -m integration) -----


@pytest.mark.integration
async def test_2_11_live_search_pembrolizumab():
    client = CTGovClient(Settings(_env_file=None))
    client.page_size = 5  # keep the smoke payload light (still exercises the loop)
    req = DataRequirement(
        requirement_id="smoke",
        retrieval_strategy="study_search",
        search_params={"query.intr": "Pembrolizumab"},
        filter_params={},
    )
    records, trunc = await client.search_studies(req, max_records=2)
    assert len(records) == 2
    assert all(isinstance(r, StudyRecord) for r in records)
    assert all(r.nct_id.startswith("NCT") for r in records)
    assert trunc is not None and trunc.total_available > 2
    assert client.api_calls and client.api_calls[0].http_status == 200
