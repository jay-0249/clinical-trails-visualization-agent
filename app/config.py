"""Application settings, loaded from environment / .env.

Two OpenAI models are configured independently (see docs/DECISIONS.md, Phase 0):
- llm_model_main     -> Stage 1 query analysis (the planner / reasoning call)
- llm_model_subagent -> Stage 4 viz generation, and other secondary LLM calls
                        (e.g. Stage 2.5 free-text extraction, v2)

OPENAI_API_KEY is read from the environment (or .env). It is optional at load
time so Phases 2-6 (deterministic, no LLM) run without it; the query analyzer
raises a clear error if it is still missing when Stage 1 runs.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # LLM (OpenAI)
    openai_api_key: str | None = None
    llm_model_main: str = "gpt-4o"  # Stage 1: query analysis (planner)
    llm_model_subagent: str = "gpt-4o-mini"  # Stage 4: viz gen + secondary calls

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
