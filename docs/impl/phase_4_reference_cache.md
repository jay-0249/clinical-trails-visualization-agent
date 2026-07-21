# Phase 4: Reference Data Cache

**File to create:** `app/services/reference_cache.py`

---

## What to fetch at startup

```python
class ReferenceDataCache:
    enums: dict[str, list[str]]          # field -> valid values
    field_metadata: dict                  # from /studies/metadata
    api_version: str
    last_refresh: str

    # Convenience accessors (derived from enums)
    valid_phases: list[str]
    valid_statuses: list[str]
    valid_sponsor_classes: list[str]
    groupable_fields: list[str]          # from StudyRecord model fields

    async def load(self):
        """Call at startup. Fetches from 3 endpoints."""
        # GET /studies/enums
        # GET /studies/metadata
        # GET /version
```

## Endpoints

1. `GET /studies/enums` → dict of field name → list of valid values
2. `GET /studies/metadata` → field metadata (types, paths)
3. `GET /version` → `{"apiVersion": "...", "dataTimestamp": "..."}`

## Fallback

If any startup fetch fails, log a WARNING and use hardcoded fallback values:

```python
FALLBACK_PHASES = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]
FALLBACK_STATUSES = ["RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING",
                     "COMPLETED", "TERMINATED", "WITHDRAWN", "SUSPENDED",
                     "ENROLLING_BY_INVITATION"]
FALLBACK_SPONSOR_CLASSES = ["INDUSTRY", "NIH", "FED", "OTHER"]
```

NOTE: these fallbacks exist ONLY for startup resilience. Pipeline code must use `reference_cache.valid_phases`, never the fallback constants directly.

## groupable_fields

Derive from `StudyRecord` model fields at initialization:

```python
groupable_fields = list(StudyRecord.model_fields.keys())
```

## Tool schemas for Stage 1 prompt

Prepare tool descriptions that get injected into the query analyzer prompt:

```python
tool_schemas = [
    {"name": "search_studies", "description": "Search for studies with query/filter params. Returns individual records.", ...},
    {"name": "get_field_stats", "description": "Pre-aggregated counts for a field. One API call, any scale, no citations.", ...},
    {"name": "get_study_detail", "description": "Full details for one NCT ID.", ...},
]
```

---

## Checkpoint

- Cache loads from live API
- valid_phases contains expected values
- Graceful fallback when API unreachable
- No automated test file — manual verification
