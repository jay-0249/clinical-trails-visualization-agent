"""Stage 1 — NL query -> QueryIntent (the one LLM planning call).

Uses the OpenAI SDK directly in JSON mode (not LangChain, and not strict
structured outputs): DataRequirement.search_params/filter_params are free-form
dicts that strict json_schema cannot represent, so we ask for a JSON object,
validate it against the Pydantic QueryIntent, and retry once with the error if
the first attempt is malformed.
"""

import json
import logging
import time

from openai import AsyncOpenAI
from pydantic import ValidationError

from app.config import settings
from app.prompts.query_analyzer import build_query_analyzer_prompt
from app.schemas.intent import QueryIntent
from app.services.reference_cache import ReferenceDataCache
from app.utils.logger import get_logger, log_event

_logger = get_logger("query_analyzer")


class QueryAnalysisError(RuntimeError):
    """Stage 1 could not produce a valid QueryIntent."""


def _client() -> AsyncOpenAI:
    if not settings.openai_api_key:
        raise QueryAnalysisError(
            "OPENAI_API_KEY is not set — Stage 1 (query analysis) requires it."
        )
    return AsyncOpenAI(api_key=settings.openai_api_key)


async def analyze(
    query: str,
    confirmed_filters: dict,
    input_mode: str,
    reference_cache: ReferenceDataCache,
    request_id: str | None = None,
) -> QueryIntent:
    """NL query + confirmed filters -> validated QueryIntent."""
    client = _client()
    valid_enums = {
        "Phase": reference_cache.valid_phases,
        "Status": reference_cache.valid_statuses,
        "AgencyClass": reference_cache.valid_sponsor_classes,
    }
    system_prompt = build_query_analyzer_prompt(
        valid_enums=valid_enums,
        groupable_fields=reference_cache.groupable_fields,
        tool_schemas=reference_cache.tool_schemas,
        input_mode=input_mode,
        confirmed_filters=confirmed_filters,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"QUERY: {query}\n\nOutput the QueryIntent JSON now."},
    ]

    last_error: Exception | None = None
    for attempt in range(2):  # 1 try + 1 corrective retry
        start = time.perf_counter()
        resp = await client.chat.completions.create(
            model=settings.llm_model_query_analyzer,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0,
        )
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        content = resp.choices[0].message.content or ""

        try:
            intent = QueryIntent.model_validate(json.loads(content))
            intent.original_query = query  # trust the real query, not a paraphrase
            log_event(
                _logger,
                logging.INFO,
                "llm_call",
                request_id=request_id,
                stage="query_analyzer",
                model=resp.model,
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                duration_ms=duration_ms,
                attempt=attempt + 1,
                output_valid=True,
            )
            return intent
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = exc
            log_event(
                _logger,
                logging.WARNING,
                "llm_call",
                request_id=request_id,
                stage="query_analyzer",
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
                            "Output ONLY a single valid JSON object matching the "
                            "QueryIntent schema exactly, with no surrounding text."
                        ),
                    }
                )

    raise QueryAnalysisError(
        f"Stage 1 produced an invalid QueryIntent after a retry: {last_error}"
    )
