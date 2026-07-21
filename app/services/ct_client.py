"""Async ClinicalTrials.gov API v2 client.

Handles cursor pagination, retry/backoff, rate limiting, and — critically —
normalizes every raw study into a typed StudyRecord the moment it arrives, so
nothing downstream ever touches the messy, all-nullable API JSON.

Instantiate one client per request: it accumulates APICallRecords in
`self.api_calls` for the response metadata (no cross-request state).
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.config import Settings
from app.schemas.intent import DataRequirement
from app.schemas.trial_record import APICallRecord, FieldStatRecord, StudyRecord
from app.utils.date_parser import parse_date
from app.utils.helpers import safe_get
from app.utils.logger import get_logger, log_event

# Restrict the payload to the fields we normalize.
FIELDS = (
    "NCTId,BriefTitle,OverallStatus,Phase,Condition,InterventionName,"
    "InterventionType,LeadSponsorName,LeadSponsorClass,StartDate,CompletionDate,"
    "LocationCity,LocationState,LocationCountry,EnrollmentCount,StudyType,BriefSummary"
)


@dataclass
class TruncationInfo:
    total_available: int
    returned: int
    reason: str


# --- normalization (pure, sync, never raises) -----------------------------


def _format_phase(p: str) -> str:
    """Format one CT.gov phase enum token for display (general transform)."""
    if p == "NA":
        return "N/A"
    if p.startswith("EARLY_PHASE"):
        return "Early Phase " + p[len("EARLY_PHASE") :]
    if p.startswith("PHASE"):
        return "Phase " + p[len("PHASE") :]
    return " ".join(w.capitalize() for w in p.split("_"))  # generic fallback


def phase_label(phases: list[str]) -> str:
    if not phases:
        return "N/A"
    return "/".join(_format_phase(p) for p in phases)


def _unique(items) -> list[str]:
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def normalize_study(raw: dict, source_query: str = "") -> StudyRecord:
    """Map a raw CT.gov study dict to a StudyRecord. Safe on any missing field."""
    phases = safe_get(raw, "protocolSection.designModule.phases", []) or []
    interventions_raw = (
        safe_get(raw, "protocolSection.armsInterventionsModule.interventions", []) or []
    )
    locations = safe_get(raw, "protocolSection.contactsLocationsModule.locations", []) or []

    start_year, start_month = parse_date(
        safe_get(raw, "protocolSection.statusModule.startDateStruct")
    )
    completion_year, _ = parse_date(
        safe_get(raw, "protocolSection.statusModule.completionDateStruct")
    )

    return StudyRecord(
        nct_id=safe_get(raw, "protocolSection.identificationModule.nctId", ""),
        title=safe_get(raw, "protocolSection.identificationModule.briefTitle", ""),
        status=safe_get(raw, "protocolSection.statusModule.overallStatus", ""),
        phases=phases,
        phase_label=phase_label(phases),
        conditions=safe_get(raw, "protocolSection.conditionsModule.conditions", []) or [],
        interventions=[
            i["name"] for i in interventions_raw if isinstance(i, dict) and i.get("name")
        ],
        intervention_types=[
            i["type"] for i in interventions_raw if isinstance(i, dict) and i.get("type")
        ],
        sponsor_name=safe_get(
            raw, "protocolSection.sponsorCollaboratorsModule.leadSponsor.name"
        ),
        sponsor_class=safe_get(
            raw, "protocolSection.sponsorCollaboratorsModule.leadSponsor.class"
        ),
        start_year=start_year,
        start_month=start_month,
        completion_year=completion_year,
        countries=_unique(
            loc.get("country") for loc in locations if isinstance(loc, dict)
        ),
        cities=_unique(loc.get("city") for loc in locations if isinstance(loc, dict)),
        enrollment=safe_get(raw, "protocolSection.designModule.enrollmentInfo.count"),
        study_type=safe_get(raw, "protocolSection.designModule.studyType"),
        excerpt=safe_get(raw, "protocolSection.descriptionModule.briefSummary", "") or "",
        source_query=source_query,
    )


# --- client ---------------------------------------------------------------


class CTGovClient:
    def __init__(self, settings: Settings, request_id: str | None = None):
        self.base_url = settings.ct_api_base_url.rstrip("/")
        self.page_size = settings.ct_api_page_size
        self.max_pages = settings.ct_api_max_pages
        self.timeout = settings.ct_api_timeout_seconds
        self.rate_delay = settings.ct_api_rate_limit_delay
        self.request_id = request_id
        self.api_calls: list[APICallRecord] = []
        self._logger = get_logger("ct_client")

    def _log_call(self, endpoint, params, status, count, duration_ms, error=None):
        self.api_calls.append(
            APICallRecord(
                endpoint=endpoint,
                params={k: v for k, v in params.items() if k != "fields"},
                timestamp=datetime.now(timezone.utc).isoformat(),
                record_count=count,
                http_status=status,
                duration_ms=int(duration_ms),
            )
        )
        log_event(
            self._logger,
            logging.INFO,
            "api_call",
            request_id=self.request_id,
            endpoint=endpoint,
            http_status=status,
            record_count=count,
            duration_ms=duration_ms,
            error=error,
        )

    async def _request(
        self, client: httpx.AsyncClient, endpoint: str, params: dict
    ) -> dict | list:
        """GET with exponential backoff on 429/5xx and transport errors (max 3 retries)."""
        url = f"{self.base_url}{endpoint}"
        for attempt in range(4):  # 1 try + 3 retries
            start = time.perf_counter()
            try:
                resp = await client.get(url, params=params, timeout=self.timeout)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                dur = round((time.perf_counter() - start) * 1000, 1)
                self._log_call(endpoint, params, 0, 0, dur, error=str(exc))
                if attempt == 3:
                    raise
                await asyncio.sleep(2**attempt)
                continue

            dur = round((time.perf_counter() - start) * 1000, 1)
            if resp.status_code == 429 or resp.status_code >= 500:
                self._log_call(endpoint, params, resp.status_code, 0, dur)
                if attempt == 3:
                    resp.raise_for_status()
                await asyncio.sleep(2**attempt)
                continue

            resp.raise_for_status()  # other 4xx -> raise immediately, no retry
            data = resp.json()
            if isinstance(data, dict):
                count = (
                    len(data.get("studies", []))
                    if "studies" in data
                    else (1 if "protocolSection" in data else 0)
                )
            elif isinstance(data, list):
                count = len(data)
            else:
                count = 0
            self._log_call(endpoint, params, resp.status_code, count, dur)
            return data
        raise RuntimeError("request retries exhausted")  # unreachable

    async def search_studies(
        self, req: DataRequirement, max_records: int
    ) -> tuple[list[StudyRecord], TruncationInfo | None]:
        params = {**(req.search_params or {}), **(req.filter_params or {})}
        params["pageSize"] = self.page_size
        params["countTotal"] = "true"
        params["fields"] = FIELDS

        records: list[StudyRecord] = []
        total: int | None = None
        page_token: str | None = None

        async with httpx.AsyncClient() as client:
            for _page in range(self.max_pages):
                if page_token:
                    params["pageToken"] = page_token
                data = await self._request(client, "/studies", params)
                if total is None:
                    total = data.get("totalCount")
                for rawstudy in data.get("studies", []) or []:
                    records.append(
                        normalize_study(rawstudy, source_query=req.requirement_id)
                    )
                    if len(records) >= max_records:
                        break
                page_token = data.get("nextPageToken")
                if len(records) >= max_records or not page_token:
                    break
                await asyncio.sleep(self.rate_delay)  # ~50 req/min ceiling

        trunc = None
        if total is not None and len(records) < total:
            trunc = TruncationInfo(
                total_available=total,
                returned=len(records),
                reason="Reached max_studies cap or page limit",
            )
        return records, trunc

    async def get_field_stats(
        self, field_name: str, filter_params: dict
    ) -> list[FieldStatRecord]:
        params = {"fields": field_name, "types": "ENUM", **(filter_params or {})}
        async with httpx.AsyncClient() as client:
            data = await self._request(client, "/stats/field/values", params)
        out: list[FieldStatRecord] = []
        for block in data or []:
            for tv in block.get("topValues", []) or []:
                out.append(
                    FieldStatRecord(
                        field_name=field_name,
                        field_value=str(tv.get("value", "")),
                        count=int(tv.get("studiesCount", 0)),
                    )
                )
        return out

    async def get_study_detail(self, nct_id: str) -> StudyRecord:
        params = {"fields": FIELDS}
        async with httpx.AsyncClient() as client:
            data = await self._request(client, f"/studies/{nct_id}", params)
        return normalize_study(data, source_query=nct_id)
