"""Application settings, loaded from environment / .env.

Each LLM stage picks its own OpenAI model (see docs/DECISIONS.md):
- llm_model_query_analyzer -> Stage 1 query analysis (the planner / reasoning call)
- llm_model_viz_generator  -> Stage 4 visualization-spec generation
- llm_model_extractor      -> Stage 2.5 free-text extraction (v2)

OPENAI_API_KEY is read from the environment (or .env). It is optional at load
time so Phases 2-6 (deterministic, no LLM) run without it; the query analyzer
raises a clear error if it is still missing when Stage 1 runs.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (OpenAI) — one model per stage
    openai_api_key: str | None = None
    # Stage 1: planning. Dated snapshot — this key has no bare `gpt-4o` alias access.
    llm_model_query_analyzer: str = "gpt-4o-2024-08-06"
    llm_model_viz_generator: str = "gpt-5.4-nano"  # Stage 4: viz spec (reliable hints)
    llm_model_extractor: str = "gpt-4o-mini"  # Stage 2.5: extraction (v2)

    # ClinicalTrials.gov API v2 (no key required)
    ct_api_base_url: str = "https://clinicaltrials.gov/api/v2"
    ct_api_page_size: int = 1000  # always page at the API max
    ct_api_max_pages: int = 10  # 10 * 1000 = 10000 study safety ceiling
    ct_api_timeout_seconds: int = 30
    ct_api_rate_limit_delay: float = 1.2  # ~50 req/min ceiling

    # Pipeline
    max_studies: int = 5000  # default cap; QueryRequest.max_studies overrides
    log_level: str = "INFO"


settings = Settings()
