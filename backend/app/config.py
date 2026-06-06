"""Typed application settings loaded from env vars or .env file."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import List

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    app_name: str = "AMR Predictive Maintenance API"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    database_url: str = "postgresql+asyncpg://amr:amr@localhost:5432/amr_pdm"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 14


    cors_origins_raw: str = Field(
        default="http://localhost:5173",
        validation_alias=AliasChoices("CORS_ORIGINS", "cors_origins", "cors_origins_raw"),
    )

    mqtt_enabled: bool = False
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883
    mqtt_topic_pattern: str = "factory/+/+/telemetry/#"

    @computed_field
    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    s = Settings()
    if s.app_env == "production" and s.jwt_secret in (
        "change-me", "dev-secret-change-in-prod",
        "please-override-in-real-deployments",
    ):
        log.warning(
            "JWT_SECRET is left at a default value in production. "
            "Set a strong random secret via environment.",
        )
    return s
