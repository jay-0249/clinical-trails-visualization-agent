"""Stage 4 — aggregated data -> VisualizationSpec (the second/subagent LLM call).

The LLM chooses `type` (open string), `type_category` (7 Literals), `encoding`,
`title`, and `rendering_hints`. It never supplies the data: after validation we
inject the real aggregated rows into `spec.data`, so "never invent data" is a
structural guarantee, not just a prompt instruction. We also verify the encoding
matches the category's contract and references real data columns, retrying once
with the error on failure.
"""

import json
import logging
import time

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.prompts.viz_generator import build_viz_generator_prompt
from app.schemas.intent import AnalysisTask
from app.schemas.response import VisualizationSpec
from app.utils.logger import get_logger, log_event

_logger = get_logger("viz_generator")

# Keys each type_category's encoding must define (temporal has a Gantt alt).
_ENCODING_REQUIRED = {
    "categorical": ["category", "value"],
    "temporal": ["time", "value"],
    "relational": ["source", "target", "weight"],
    "spatial": ["location", "value"],
    "matrix": ["x", "y", "color"],
    "hierarchical": ["levels", "value"],
    "distribution": ["value"],
}

# Fallback color_scheme per category when the model omits rendering_hints.
# Belt-and-suspenders: the configured model (gpt-5.4-nano) emits hints reliably,
# but this guarantees the frontend always has a color_scheme if a model regresses.
_DEFAULT_SCHEME = {
    "categorical": "categorical",
    "temporal": "categorical",
    "relational": "categorical",
    "spatial": "sequential_blue",
    "matrix": "sequential_blue",
    "hierarchical": "categorical",
    "distribution": "sequential_blue",
}

# Synonym -> contract key per category. A small model sometimes names an encoding
# key off-contract (e.g. spatial "country" instead of "location"); we rename it
# so the frontend always receives the contract keys.
_ENCODING_SYNONYMS = {
    "spatial": {"country": "location", "region": "location", "geo": "location", "area": "location"},
    "categorical": {"label": "category", "name": "category", "group": "category"},
    "relational": {"from": "source", "node1": "source", "to": "target", "node2": "target"},
}


def _normalize_encoding(spec: VisualizationSpec, request_id: str | None = None) -> None:
    """Rename known synonym encoding keys to the contract keys (mutates spec)."""
    synonyms = _ENCODING_SYNONYMS.get(spec.type_category)
    if not synonyms or not isinstance(spec.encoding, dict):
        return
    renamed = {}
    for old, new in synonyms.items():
        if old in spec.encoding and new not in spec.encoding:
            spec.encoding[new] = spec.encoding.pop(old)
            renamed[old] = new
    if renamed:
        log_event(
            _logger,
            logging.INFO,
            "encoding_normalized",
            request_id=request_id,
            type_category=spec.type_category,
            renamed=renamed,
        )


class VizGenerationError(RuntimeError):
    """Stage 4 could not produce a valid VisualizationSpec."""


def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise VizGenerationError(
            "OPENAI_API_KEY is not set — Stage 4 (viz generation) requires it."
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


def _data_columns(rows: list[dict]) -> set:
    cols: set = set()
    for r in rows:
        cols.update(r.keys())
    return cols


def _encoding_field_refs(encoding) -> list[str]:
    """Every {"field": "<col>"} reference anywhere in the encoding tree."""
    refs: list[str] = []

    def walk(node):
        if isinstance(node, dict):
            field = node.get("field")
            if isinstance(field, str):
                refs.append(field)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(encoding)
    return refs


def _verify_encoding(spec: VisualizationSpec, aggregated_data: list[dict]) -> None:
    cat = spec.type_category
    enc = spec.encoding or {}

    required = _ENCODING_REQUIRED.get(cat, [])
    if cat == "temporal" and "time" not in enc and "time_start" in enc:
        required = ["time_start", "time_end"]  # Gantt/interval form
    missing = [k for k in required if k not in enc]
    if missing:
        raise VizGenerationError(
            f"encoding for type_category '{cat}' is missing {missing}; "
            f"the contract requires {required}."
        )

    if aggregated_data:
        cols = _data_columns(aggregated_data)
        bad = [f for f in _encoding_field_refs(enc) if f not in cols]
        if bad:
            raise VizGenerationError(
                f"encoding references columns not present in the data: {bad}. "
                f"Available columns: {sorted(cols)}"
            )


async def generate(
    task: AnalysisTask,
    aggregated_data: list[dict],
    original_query: str,
    request_id: str | None = None,
    model: str | None = None,
) -> VisualizationSpec:
    """Aggregated data -> validated VisualizationSpec (data injected, not trusted).

    `model` overrides settings.llm_model_viz_generator (used by diagnostics).
    """
    client = _client()
    model = model or settings.llm_model_viz_generator
    system_prompt = build_viz_generator_prompt(task, aggregated_data, original_query)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Output the VisualizationSpec JSON now."},
    ]

    last_error: Exception | None = None
    for attempt in range(2):  # 1 try + 1 corrective retry
        start = time.perf_counter()
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        content = resp.choices[0].message.content or ""

        try:
            spec = VisualizationSpec.model_validate(json.loads(content))
            _normalize_encoding(spec, request_id)
            _verify_encoding(spec, aggregated_data)
            # Trust code, not the LLM, for identity + data.
            spec.task_id = task.task_id
            spec.data = aggregated_data
            if not spec.rendering_hints:  # defensive fallback if the model omits them
                spec.rendering_hints = {
                    "color_scheme": _DEFAULT_SCHEME.get(spec.type_category, "categorical")
                }
            log_event(
                _logger,
                logging.INFO,
                "llm_call",
                request_id=request_id,
                stage="viz_generator",
                model=resp.model,
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                output_valid=True,
                viz_type=spec.type,
                type_category=spec.type_category,
            )
            return spec
        except (json.JSONDecodeError, ValidationError, VizGenerationError) as exc:
            last_error = exc
            log_event(
                _logger,
                logging.WARNING,
                "llm_call",
                request_id=request_id,
                stage="viz_generator",
                model=resp.model,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                output_valid=False,
                error=str(exc)[:400],
            )
            if attempt == 0:
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output was invalid:\n{str(exc)[:600]}\n\n"
                            "Output ONLY a single valid VisualizationSpec JSON object. "
                            "Use the EXACT column names present in the data for every "
                            "encoding field, and match the encoding contract for your "
                            "chosen type_category."
                        ),
                    }
                )

    raise VizGenerationError(
        f"Stage 4 produced an invalid VisualizationSpec after a retry: {last_error}"
    )
