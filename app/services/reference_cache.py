"""Startup cache of CT.gov reference data: enums, field metadata, API version.

Loaded once at app startup and read (never mutated) by the pipeline. Each of
the three fetches is guarded independently — if one endpoint is unreachable we
log a WARNING and fall back to a static list for that piece only, so the
service still starts.

IMPORTANT: the FALLBACK_* constants below exist ONLY for startup resilience.
Pipeline code must read `cache.valid_phases` / `.valid_statuses` / etc. — never
the constants directly — so validation always tracks the live enum set when the
API is reachable.
"""

import logging

import httpx

from app.config import Settings
from app.schemas.trial_record import StudyRecord
from app.utils.logger import get_logger, log_event

FALLBACK_PHASES = ["EARLY_PHASE1", "PHASE1", "PHASE2", "PHASE3", "PHASE4", "NA"]
FALLBACK_STATUSES = [
    "RECRUITING",
    "NOT_YET_RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "COMPLETED",
    "TERMINATED",
    "WITHDRAWN",
    "SUSPENDED",
    "ENROLLING_BY_INVITATION",
]
FALLBACK_SPONSOR_CLASSES = ["INDUSTRY", "NIH", "FED", "OTHER"]

# Tool descriptions injected into the Stage 1 (query analyzer) prompt so the LLM
# knows which retrieval strategies exist and what params each accepts.
TOOL_SCHEMAS = [
    {
        "name": "search_studies",
        "description": (
            "Search studies and return individual normalized records "
            "(supports citations). The default strategy for most queries."
        ),
        "search_params": [
            "query.cond",
            "query.intr",
            "query.term",
            "query.spons",
            "query.locn",
        ],
        "filter_params": ["filter.overallStatus", "filter.phase", "filter.geo"],
    },
    {
        "name": "get_field_stats",
        "description": (
            "Pre-aggregated value counts for one enum field. One API call, any "
            "scale, no citations. Use for broad distributions when individual "
            "records are not needed."
        ),
        "params": ["field_name", "filter_params"],
    },
    {
        "name": "get_study_detail",
        "description": "Full normalized details for a single NCT ID.",
        "params": ["nct_id"],
    },
]


class ReferenceDataCache:
    def __init__(self, settings: Settings):
        self.base_url = settings.ct_api_base_url.rstrip("/")
        self.timeout = settings.ct_api_timeout_seconds

        self.enums: dict[str, list[str]] = {}
        self.field_metadata: list = []
        self.api_version: str = ""
        self.last_refresh: str = ""

        # Convenience accessors — start on the static fallback, overwritten on load.
        self.valid_phases: list[str] = list(FALLBACK_PHASES)
        self.valid_statuses: list[str] = list(FALLBACK_STATUSES)
        self.valid_sponsor_classes: list[str] = list(FALLBACK_SPONSOR_CLASSES)
        self.groupable_fields: list[str] = list(StudyRecord.model_fields.keys())

        self.tool_schemas = TOOL_SCHEMAS
        self.loaded = False
        self._logger = get_logger("reference_cache")

    async def _get(self, client: httpx.AsyncClient, endpoint: str):
        resp = await client.get(f"{self.base_url}{endpoint}", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def _warn(self, event: str, exc: Exception) -> None:
        log_event(self._logger, logging.WARNING, event, error=str(exc))

    async def load(self) -> None:
        """Fetch enums, metadata, and version at startup. Never raises."""
        async with httpx.AsyncClient() as client:
            await self._load_enums(client)
            await self._load_metadata(client)
            await self._load_version(client)
        self.loaded = True

    async def _load_enums(self, client: httpx.AsyncClient) -> None:
        try:
            data = await self._get(client, "/studies/enums")
        except Exception as exc:  # noqa: BLE001 - startup resilience: any failure -> fallback
            self._warn("reference_enums_fallback", exc)
            return
        enums: dict[str, list[str]] = {}
        for entry in data or []:
            etype = entry.get("type")
            values = [
                v["value"]
                for v in entry.get("values", []) or []
                if isinstance(v, dict) and v.get("value")
            ]
            if etype:
                enums[etype] = values
        if enums:
            self.enums = enums
            self.valid_phases = enums.get("Phase", self.valid_phases)
            self.valid_statuses = enums.get("Status", self.valid_statuses)
            self.valid_sponsor_classes = enums.get(
                "AgencyClass", self.valid_sponsor_classes
            )
            log_event(
                self._logger,
                logging.INFO,
                "reference_enums_loaded",
                enum_types=len(enums),
                phases=len(self.valid_phases),
                statuses=len(self.valid_statuses),
            )

    async def _load_metadata(self, client: httpx.AsyncClient) -> None:
        try:
            self.field_metadata = await self._get(client, "/studies/metadata") or []
        except Exception as exc:  # noqa: BLE001
            self._warn("reference_metadata_fallback", exc)

    async def _load_version(self, client: httpx.AsyncClient) -> None:
        try:
            data = await self._get(client, "/version")
        except Exception as exc:  # noqa: BLE001
            self._warn("reference_version_fallback", exc)
            return
        self.api_version = data.get("apiVersion", "")
        self.last_refresh = data.get("dataTimestamp", "")
