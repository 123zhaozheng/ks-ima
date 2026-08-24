"""Validated, immutable application configuration."""

from __future__ import annotations

import re
from functools import lru_cache
from ipaddress import ip_network
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Settings read from environment without exposing secret values."""

    model_config = SettingsConfigDict(
        env_prefix="IMA_", extra="ignore", frozen=True, case_sensitive=False
    )

    environment: Literal["development", "test", "staging", "production"] = "development"
    build_version: str = "dev"
    public_origin: str = "http://localhost:8080"
    trusted_proxies: Annotated[tuple[str, ...], NoDecode] = ()
    database_url: SecretStr = SecretStr("postgresql+asyncpg://postgres:pass@localhost:5432/app")
    database_schema: str = "ima"
    cors_origins: Annotated[tuple[str, ...], NoDecode] = ()
    max_body_bytes: int = 25 * 1024 * 1024
    log_level: str = "INFO"
    task_database_url: SecretStr | None = None
    task_schema: str = "ima_jobs"
    diagnostic_jobs_enabled: bool = False
    worker_heartbeat_seconds: int = 15
    worker_lag_warning_seconds: int = 120
    diagnostic_queue: str = "diagnostic"
    worker_name: str = "diagnostic-worker"

    @field_validator("public_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("public_origin must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("public_origin cannot contain query or fragment")
        return value.rstrip("/")

    @field_validator("trusted_proxies", mode="before")
    @classmethod
    def parse_proxies(cls, value: object) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        values = value.split(",") if isinstance(value, str) else value
        if not isinstance(values, list | tuple):
            raise ValueError("trusted_proxies must be a comma-separated list")
        result = tuple(str(item).strip() for item in values if str(item).strip())
        for network in result:
            ip_network(network, strict=False)
        return result

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_origins(cls, value: object) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        values = value.split(",") if isinstance(value, str) else value
        if not isinstance(values, list | tuple):
            raise ValueError("cors_origins must be a comma-separated list")
        result = tuple(str(item).strip().rstrip("/") for item in values if str(item).strip())
        if "*" in result:
            raise ValueError("wildcard CORS origins are not allowed")
        for origin in result:
            parsed = urlparse(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("cors_origins must contain absolute HTTP(S) URLs")
        return result

    @field_validator("database_schema", "task_schema")
    @classmethod
    def validate_schema_name(cls, value: str) -> str:
        if not value.isidentifier():
            raise ValueError("schema names must be valid identifiers")
        return value

    @field_validator("max_body_bytes")
    @classmethod
    def validate_body_limit(cls, value: int) -> int:
        if value <= 0 or value > 512 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 and 536870912")
        return value

    @field_validator("diagnostic_queue", "worker_name")
    @classmethod
    def validate_runtime_identity(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value):
            raise ValueError(
                "runtime identities must use lowercase ASCII letters, digits, '.', '_' or '-'"
            )
        return value

    @model_validator(mode="after")
    def validate_environment_constraints(self) -> Settings:
        if self.environment == "production":
            if not self.public_origin.startswith("https://"):
                raise ValueError("production public_origin must use HTTPS")
            if not self.cors_origins:
                raise ValueError("production requires explicit CORS origins")
            if self.database_url.get_secret_value().endswith("postgres:pass@localhost:5432/app"):
                raise ValueError("production cannot use the development database credential")
        return self

    @property
    def task_url(self) -> str:
        return (self.task_database_url or self.database_url).get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
