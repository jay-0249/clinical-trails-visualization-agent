**Base URL:** `https://clinicaltrials.gov/api/v2`

**Auth:** None required (public API)

**Rate limit:** ~50 requests/minute

---

## Endpoints

| Endpoint                    | Purpose                    | Our usage                       |
| --------------------------- | -------------------------- | ------------------------------- |
| `GET /studies`              | Search studies             | Primary data source (paginated) |
| `GET /studies/{NCT_ID}`     | Single study               | Specific study lookup           |
| `GET /studies/enums`        | Valid enum values          | Startup cache for validation    |
| `GET /studies/metadata`     | Field data model           | Startup cache for field info    |
| `GET /studies/search-areas` | Search area mappings       | Documentation                   |
| `GET /stats/field/values`   | Field value distribution   | Broad distribution queries      |
| `GET /stats/field/sizes`    | Field cardinality          | Informational                   |
| `GET /stats/size`           | DB statistics              | Informational                   |
| `GET /version`              | API version + data refresh | Startup cache for metadata      |

## Search Parameters (free-text, forgiving)

- `query.cond` — condition/disease
- `query.intr` — intervention/drug name
- `query.term` — general full-text
- `query.spons` — sponsor name
- `query.locn` — geographic location

## Filter Parameters (enum-based, strict)

- `filter.overallStatus` — pipe-delimited: `RECRUITING|COMPLETED|...`
- `filter.geo` — `distance(lat,lon,dist)`
- **Phase has no `filter.phase` param** (a request with it returns 400). Filter
  phase via the advanced/Essie expression instead:
  `filter.advanced=AREA[Phase]PHASE3` (single) or
  `filter.advanced=AREA[Phase](PHASE1 OR PHASE2)` (multiple). Internally we keep
  `filter.phase` as the semantic key and `ct_client._translate_phase_filter`
  converts it at the HTTP boundary.

## Pagination

- `pageSize` — max 1000 (default 10, always override)
- `pageToken` — cursor from `nextPageToken` in response
- `countTotal=true` — include total count

## Response Structure

```
study.protocolSection.identificationModule     → nctId, briefTitle, organization
study.protocolSection.statusModule             → overallStatus, startDateStruct, completionDateStruct
study.protocolSection.designModule             → phases[], designInfo, enrollmentInfo
study.protocolSection.conditionsModule          → conditions[]
study.protocolSection.armsInterventionsModule   → interventions[{type, name}]
study.protocolSection.sponsorCollaboratorsModule → leadSponsor{name, class}
study.protocolSection.contactsLocationsModule   → locations[{facility, city, state, country}]
study.protocolSection.descriptionModule        → briefSummary, detailedDescription
```

## Known Data Quirks

1. **Dates are inconsistent** — mix of `"2024-01-15"`, `"January 2024"`, `"January 15, 2024"`. Normalize during StudyRecord creation.
2. **Nullable everything** — phases, conditions, interventions, locations, sponsors can all be null or empty. Safe get with fallback for every field.
3. **Phases is a list** — `["PHASE1", "PHASE2"]` for combined phases. Create display label `"Phase 1/Phase 2"`.
4. **Location data is nested arrays** — each location has facility, city, state, country. Extract and flatten.

## Normalization Mapping

See `docs/impl/phase_3_api_client.md` for the full field-by-field mapping from API response paths to `StudyRecord` fields.
