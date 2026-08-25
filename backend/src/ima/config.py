"""Validated, immutable application configuration."""

from __future__ import annotations

import re
from functools import lru_cache
from ipaddress import ip_network
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, SecretStr, field_validator, model_validator
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
    session_cookie_name: str = "ima_session"
    csrf_cookie_name: str = "ima_csrf"
    session_pepper: SecretStr = SecretStr("development-session-pepper-change-me")
    token_pepper: SecretStr = SecretStr("development-token-pepper-change-me")
    totp_encryption_key: SecretStr = SecretStr("development-totp-key-change-me-32bytes!")
    bridge_token: SecretStr = SecretStr("development-bridge-token-change-me")
    python_api_internal_url: str = "http://api:8000"
    bridge_timeout_ms: int = 1500
    session_idle_seconds: int = 86400
    session_absolute_seconds: int = 2592000
    recent_auth_seconds: int = 900
    login_window_seconds: int = 300
    login_max_attempts: int = 10
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from: str | None = None
    allow_registration: bool = False
    # Central model-governance controls.  The key ring is deliberately a
    # SecretStr so settings repr/logging can never expose its contents.
    model_key_ring: SecretStr = SecretStr('{"v1":"development-model-key-change-me-32bytes!"}')
    model_current_key_version: str = "v1"
    model_fingerprint_key: SecretStr = SecretStr("development-model-fingerprint-change-me-32bytes!")
    model_custom_ca_dir: str | None = None
    model_allowed_hosts: Annotated[tuple[str, ...], NoDecode] = ()
    model_allowed_cidrs: Annotated[tuple[str, ...], NoDecode] = ()
    model_allow_insecure_private: bool = False
    model_max_response_bytes: int = 8 * 1024 * 1024
    model_connect_timeout_seconds: float = 5.0
    model_read_timeout_seconds: float = 30.0
    model_write_timeout_seconds: float = 30.0
    model_pool_timeout_seconds: float = 5.0
    model_health_min_interval_seconds: int = 30

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

    @field_validator("model_allowed_hosts", "model_allowed_cidrs", mode="before")
    @classmethod
    def parse_model_network_allowlist(cls, value: object) -> tuple[str, ...]:
        if value in (None, ""):
            return ()
        values = value.split(",") if isinstance(value, str) else value
        if not isinstance(values, list | tuple):
            raise ValueError("model network allowlists must be comma-separated lists")
        return tuple(str(item).strip().lower() for item in values if str(item).strip())

    @field_validator("model_current_key_version")
    @classmethod
    def validate_model_key_version(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,32}", value):
            raise ValueError("model_current_key_version is invalid")
        return value

    @field_validator("model_max_response_bytes")
    @classmethod
    def validate_model_response_limit(cls, value: int) -> int:
        if value < 1024 or value > 128 * 1024 * 1024:
            raise ValueError("model_max_response_bytes must be between 1024 and 134217728")
        return value

    @field_validator(
        "model_connect_timeout_seconds",
        "model_read_timeout_seconds",
        "model_write_timeout_seconds",
        "model_pool_timeout_seconds",
    )
    @classmethod
    def validate_model_timeout(cls, value: float) -> float:
        if value <= 0 or value > 300:
            raise ValueError("model timeouts must be between 0 and 300 seconds")
        return value

    @field_validator("model_health_min_interval_seconds")
    @classmethod
    def validate_model_health_interval(cls, value: int) -> int:
        if value < 1 or value > 86400:
            raise ValueError("model health interval is invalid")
        return value

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
            for key, value in {
                "session_pepper": self.session_pepper,
                "token_pepper": self.token_pepper,
                "totp_encryption_key": self.totp_encryption_key,
                "bridge_token": self.bridge_token,
            }.items():
                if "change-me" in value.get_secret_value() or len(value.get_secret_value()) < 32:
                    raise ValueError(f"production requires a high-entropy {key}")
            if "change-me" in self.model_key_ring.get_secret_value():
                raise ValueError("production requires a high-entropy model key ring")
            if "change-me" in self.model_fingerprint_key.get_secret_value():
                raise ValueError("production requires a high-entropy model fingerprint key")
        return self

    @property
    def task_url(self) -> str:
        return (self.task_database_url or self.database_url).get_secret_value()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
