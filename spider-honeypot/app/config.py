"""Application settings, read from environment variables or a .env file."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = (
        "postgresql+asyncpg://honeypot_user:honeypot_pass@localhost:5432/spider_honeypot"
    )
    log_level: str = "INFO"

    # Which honeypot variants are switched on (environment variable HONEYPOT_VARIANT):
    #   all              all three variants (the default)
    #   none             no honeypots, for the control condition
    #   semantic, prompt_injection, link_graph
    #                    only that variant
    honeypot_variant: Literal["all", "none", "semantic", "prompt_injection", "link_graph"] = "all"


@lru_cache
def get_settings() -> Settings:
    return Settings()