"""Normalized data records and the per-request pipeline context.

StudyRecord is the clean, typed shape every downstream stage works on — the
API client normalizes messy CT.gov responses into these immediately.
"""

from pydantic import BaseModel


class StudyRecord(BaseModel):
    nct_id: str
    title: str
    status: str
    phases: list[str]
    phase_label: str
    conditions: list[str]
    interventions: list[str]
    intervention_types: list[str]
    sponsor_name: str | None
    sponsor_class: str | None
    start_year: int | None
    start_month: int | None
    completion_year: int | None
    countries: list[str]
    cities: list[str]
    enrollment: int | None
    study_type: str | None
    excerpt: str
    source_query: str
    entity_tag: str | None = None


class FieldStatRecord(BaseModel):
    """One row from GET /stats/field/values — a value and its study count."""

    field_name: str
    field_value: str
    count: int


class APICallRecord(BaseModel):
    endpoint: str
    params: dict
    timestamp: str
    record_count: int
    http_status: int
    duration_ms: int


class PipelineContext(BaseModel):
    """Mutable per-request state threaded through every stage.

    No cross-request state lives here — one instance per incoming query.
    """

    request_id: str
    studies: dict[str, StudyRecord] = {}
    field_stats: list[FieldStatRecord] = []
    enums: dict[str, list[str]] = {}
    api_version: str = ""
    last_data_refresh: str = ""
    api_calls_made: list[APICallRecord] = []
    notes: list[str] = []
    limitations: list[str] = []
    warnings: list[str] = []
    conflicts: list[str] = []
    stage_timings: dict[str, float] = {}

    def add_studies(
        self, records: list[StudyRecord], entity_tag: str | None = None
    ) -> None:
        """Store records, deduping by NCT id.

        ponytail: dedup key is the bare nct_id, or "tag:nct_id" when an
        entity_tag is given — so a study matching two comparison arms
        ("Drug A vs Drug B") is kept once per arm, which is the correct
        behavior for comparative queries. Upgrade to per-arm sub-contexts
        only if an arm ever needs independent per-study metadata.
        """
        for rec in records:
            if entity_tag is not None:
                rec.entity_tag = entity_tag
            key = f"{entity_tag}:{rec.nct_id}" if entity_tag else rec.nct_id
            self.studies[key] = rec

    def get_studies_by_tags(self, tags: list[str]) -> list[StudyRecord]:
        tagset = set(tags)
        return [r for r in self.studies.values() if r.entity_tag in tagset]

    def get_all_studies(self) -> list[StudyRecord]:
        return list(self.studies.values())

    def add_note(self, note: str) -> None:
        self.notes.append(note)

    def add_limitation(self, lim: str) -> None:
        self.limitations.append(lim)

    def add_warning(self, warn: str) -> None:
        self.warnings.append(warn)

    def add_conflict(self, c: str) -> None:
        self.conflicts.append(c)
