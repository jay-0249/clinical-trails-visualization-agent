"""Stage 3 — deterministic aggregation (Layer 2 of 2).

ONE generic function, three output modes. It must never branch on a specific
field name: whatever fields the AggregationSpec names, it groups/pivots by
them. This is what lets the system answer new query shapes without code
changes (the anti-overfit guarantee).

- aggregated  -> group-by + metric        (categorical/temporal/spatial/matrix/hierarchical)
- raw_records -> pass-through value list   (distribution)
- edge_list   -> co-occurrence pairs       (relational)

Each mode function begins with a runtime guard: if it genuinely cannot proceed
(would crash on a hallucinated intent) it raises AggregationError with a clear
message; fields a mode doesn't use are logged at DEBUG and ignored. This backs
up the Stage-1 validator (Layer 1) so a bad intent fails loudly, not silently.
"""

import logging

import pandas as pd

from app.schemas.intent import AggregationSpec
from app.schemas.trial_record import StudyRecord
from app.utils.logger import get_logger, log_event

_SORT_MODES = {"value_desc", "value_asc", "key_desc", "key_asc"}
_logger = get_logger("aggregator")


class AggregationError(RuntimeError):
    """The aggregator received an intent it cannot execute."""


def aggregate(
    records: list[StudyRecord],
    spec: AggregationSpec,
    include_citations: bool = False,
    max_citations_per_group: int = 5,
) -> list[dict]:
    if not records:
        return []
    if spec.output_mode == "raw_records":
        return _raw_records(records, spec)
    if spec.output_mode == "edge_list":
        return _edge_list(records, spec, include_citations)
    return _aggregated(records, spec, include_citations, max_citations_per_group)


# --- helpers --------------------------------------------------------------


def _missing(v) -> bool:
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):  # lists/arrays aren't NA-scalars
        return False


def _native(v):
    """Coerce numpy scalars to Python; collapse whole floats (2015.0 -> 2015)."""
    if _missing(v):
        return None
    if hasattr(v, "item"):
        v = v.item()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _flatten(values) -> list:
    out = []
    for v in values:
        if isinstance(v, list):
            out.extend(x for x in v if not _missing(x))
        elif not _missing(v):
            out.append(v)
    return out


def _metric_value(sub: pd.DataFrame, spec: AggregationSpec):
    metric, field = spec.metric, spec.metric_field
    if metric == "count":
        return len(sub)
    if metric == "unique_count":
        return len(set(_flatten(sub[field]))) if field in sub else 0
    if metric == "collect":
        return _flatten(sub[field]) if field in sub else []
    if metric == "sum":
        total = sub[field].sum() if field in sub else 0
        return _native(total) if total is not None else 0
    return len(sub)  # unreachable given the Literal, but stay safe


def _sort_rows(rows: list[dict], spec: AggregationSpec) -> list[dict]:
    sb = spec.sort_by if spec.sort_by in _SORT_MODES else None
    if sb is None:
        sb = "key_asc" if spec.time_granularity else "value_desc"

    value_is_list = any(isinstance(r["value"], list) for r in rows)
    if sb in ("value_desc", "value_asc") and not value_is_list:
        rows.sort(key=lambda r: r["value"], reverse=(sb == "value_desc"))
    else:  # sort by the group key(s); "Unknown"/missing sorts last
        def keyfn(r):
            parts = []
            for f in spec.group_by:
                v = r[f]
                unknown = v == "Unknown" or v is None
                parts.append((1, 0) if unknown else (0, v))
            return tuple(parts)

        rows.sort(key=keyfn, reverse=(sb == "key_desc"))
    return rows


# --- modes (each starts with a runtime guard) -----------------------------


def _aggregated(
    records: list[StudyRecord],
    spec: AggregationSpec,
    include_citations: bool,
    max_citations: int,
) -> list[dict]:
    if not spec.group_by:
        return []  # nothing to group by
    if spec.metric in ("sum", "unique_count") and not spec.metric_field:
        raise AggregationError(
            f"metric '{spec.metric}' requires metric_field in aggregated mode"
        )

    df = pd.DataFrame([r.model_dump() for r in records])

    # Explode any list-valued group_by column (e.g. countries, interventions).
    for field in spec.group_by:
        if field in df.columns and df[field].apply(lambda v: isinstance(v, list)).any():
            df = df.explode(field)

    by = spec.group_by[0] if len(spec.group_by) == 1 else spec.group_by
    rows: list[dict] = []
    for key, sub in df.groupby(by, dropna=False):
        keyvals = key if isinstance(key, tuple) else (key,)
        row = {}
        for field, kv in zip(spec.group_by, keyvals):
            row[field] = "Unknown" if _missing(kv) else _native(kv)
        row["value"] = _metric_value(sub, spec)
        if include_citations:
            row["citations"] = [
                {"nct_id": r_nct, "excerpt": r_exc}
                for r_nct, r_exc in list(
                    zip(sub.get("nct_id", []), sub.get("excerpt", []))
                )[:max_citations]
            ]
        rows.append(row)

    return _sort_rows(rows, spec)


def _raw_records(records: list[StudyRecord], spec: AggregationSpec) -> list[dict]:
    if not spec.metric_field:
        raise AggregationError("raw_records requires metric_field (the value field)")
    field = spec.metric_field
    out: list[dict] = []
    for r in records:
        val = getattr(r, field, None)
        if val is None:
            continue
        row = {"value": val, "nct_id": r.nct_id}
        for gf in spec.group_by or []:  # extra axes for scatter plots
            row[gf] = getattr(r, gf, None)
        out.append(row)
    return out


def _edge_list(
    records: list[StudyRecord], spec: AggregationSpec, include_citations: bool
) -> list[dict]:
    if len(spec.group_by) != 2:
        raise AggregationError("edge_list requires exactly 2 group_by fields")
    if spec.metric_field:
        log_event(
            _logger,
            logging.DEBUG,
            "edge_list_metric_field_ignored",
            metric_field=spec.metric_field,
        )

    src_field, tgt_field = spec.group_by[0], spec.group_by[1]
    weights: dict[tuple, int] = {}
    cites: dict[tuple, list] = {}
    for r in records:
        for s in _as_list(getattr(r, src_field, None)):
            for t in _as_list(getattr(r, tgt_field, None)):
                if s is None or t is None:
                    continue
                edge = (s, t)
                weights[edge] = weights.get(edge, 0) + 1
                if include_citations:
                    cites.setdefault(edge, []).append(r.nct_id)

    out = []
    for (s, t), w in weights.items():
        row = {"source": s, "target": t, "weight": w}
        if include_citations:
            row["citations"] = cites.get((s, t), [])
        out.append(row)
    out.sort(key=lambda e: e["weight"], reverse=True)
    return out
