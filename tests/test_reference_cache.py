"""Phase 4 tests: graceful fallback (hermetic) + live load (integration).

The impl guide calls for manual verification; the fallback branch is the one
piece of real logic worth a persistent check, so it gets a hermetic test.
"""

import pytest

from app.config import Settings
from app.schemas.trial_record import StudyRecord
from app.services.reference_cache import (
    FALLBACK_PHASES,
    FALLBACK_STATUSES,
    ReferenceDataCache,
)


def _settings(base_url: str | None = None) -> Settings:
    s = Settings(_env_file=None)
    if base_url:
        s.ct_api_base_url = base_url
    s.ct_api_timeout_seconds = 3
    return s


async def test_graceful_fallback_when_api_unreachable():
    # localhost:1 refuses immediately -> ConnectError -> fallback, no crash, no DNS.
    cache = ReferenceDataCache(_settings("http://localhost:1/api/v2"))
    await cache.load()
    assert cache.loaded is True
    assert cache.valid_phases == FALLBACK_PHASES
    assert cache.valid_statuses == FALLBACK_STATUSES
    assert cache.enums == {}
    assert cache.field_metadata == []
    assert cache.api_version == "" and cache.last_refresh == ""


def test_groupable_fields_derived_from_model():
    cache = ReferenceDataCache(_settings())
    assert cache.groupable_fields == list(StudyRecord.model_fields.keys())
    assert "phase_label" in cache.groupable_fields
    assert "sponsor_name" in cache.groupable_fields


def test_tool_schemas_present():
    cache = ReferenceDataCache(_settings())
    names = {t["name"] for t in cache.tool_schemas}
    assert names == {"search_studies", "get_field_stats", "get_study_detail"}


@pytest.mark.integration
async def test_live_load():
    cache = ReferenceDataCache(_settings())
    await cache.load()
    assert cache.loaded
    assert "PHASE3" in cache.valid_phases
    assert "RECRUITING" in cache.valid_statuses
    assert cache.api_version  # e.g. "2.0.5"
    assert cache.last_refresh
    assert len(cache.field_metadata) > 0
    assert "Phase" in cache.enums and "Status" in cache.enums
