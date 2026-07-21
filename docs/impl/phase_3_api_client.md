**File to create:** `app/services/ct_client.py`

**Base URL:** `https://clinicaltrials.gov/api/v2`

**No API key required.**

---

## Client Class

```python
class CTGovClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.ct_api_base_url
        self.page_size = settings.ct_api_page_size
        self.max_pages = settings.ct_api_max_pages
        self.timeout = settings.ct_api_timeout_seconds
        self.rate_delay = settings.ct_api_rate_limit_delay

    async def search_studies(self, req: DataRequirement, max_records: int) -> tuple[list[StudyRecord], TruncationInfo | None]: ...
    async def get_field_stats(self, field_name: str, filter_params: dict) -> list[FieldStatRecord]: ...
    async def get_study_detail(self, nct_id: str) -> StudyRecord: ...
```

## Pagination

- Always set `pageSize=1000` (API default is 10)
- Use cursor-based pagination via `pageToken` / `nextPageToken`
- Stop when: no `nextPageToken`, or reached `max_pages`, or reached `max_records`
- Set `countTotal=true` to know total count for truncation detection

## Rate Limiting and Retry

- 1.2s `asyncio.sleep` between paginated requests
- Exponential backoff on 429 and 5xx: wait 2^attempt seconds, max 3 retries
- 30-second timeout per request via httpx
- Log every API call: endpoint, params, status_code, record_count, duration_ms

## Normalization: `normalize_study(raw: dict) -> StudyRecord`

Runs immediately when API data comes back. Uses `safe_get` for every field.

```
protocolSection.identificationModule.nctId          -> nct_id
protocolSection.identificationModule.briefTitle     -> title
protocolSection.statusModule.overallStatus          -> status
protocolSection.designModule.phases                 -> phases (list)
protocolSection.conditionsModule.conditions         -> conditions (list)
protocolSection.armsInterventionsModule.interventions -> extract .name -> interventions
protocolSection.armsInterventionsModule.interventions -> extract .type -> intervention_types
protocolSection.sponsorCollaboratorsModule.leadSponsor.name  -> sponsor_name
protocolSection.sponsorCollaboratorsModule.leadSponsor.class -> sponsor_class
protocolSection.statusModule.startDateStruct        -> parse_date -> start_year, start_month
protocolSection.statusModule.completionDateStruct   -> parse_date -> completion_year
protocolSection.contactsLocationsModule.locations    -> extract unique countries, cities
protocolSection.designModule.enrollmentInfo.count   -> enrollment
protocolSection.designModule.studyType              -> study_type
protocolSection.descriptionModule.briefSummary      -> excerpt
```

## phase_label generation

- `["PHASE1", "PHASE2"]` → `"Phase 1/Phase 2"`
- `["PHASE3"]` → `"Phase 3"`
- `[]` or `null` → `"N/A"`
- Strip "PHASE" prefix, add space: `PHASE3` → `Phase 3`, `EARLY_PHASE1` → `Early Phase 1`

## Fields to request (reduce payload)

```python
FIELDS = "NCTId,BriefTitle,OverallStatus,Phase,Condition,InterventionName,InterventionType,LeadSponsorName,LeadSponsorClass,StartDate,CompletionDate,LocationCity,LocationState,LocationCountry,EnrollmentCount,StudyType,BriefSummary"
```

---

## Test: `tests/test_ct_client.py`

- Test cases 2.1-2.10: normalization with fixture data (no live API)
- One `@pytest.mark.integration` test: fetch 2 Pembrolizumab studies from live API, verify normalization
- Test phase_label generation for all scenarios
