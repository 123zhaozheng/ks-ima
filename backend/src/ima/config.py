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
    storage_endpoint: str | None = None
    storage_region: str = "us-east-1"
    storage_bucket: str | None = None
    storage_access_key_id: SecretStr | None = Field(default=None, repr=False)
    storage_secret_access_key: SecretStr | None = Field(default=None, repr=False)
    storage_max_object_bytes: int = 25 * 1024 * 1024
    storage_presign_seconds: int = 300
    storage_connect_timeout_seconds: float = 5.0
    storage_read_timeout_seconds: float = 30.0
    storage_retention_seconds: int = 604800
    ingestion_queue: str = "ingestion"
    ingestion_max_text_bytes: int = 5 * 1024 * 1024
    ingestion_max_chunks: int = 10000
    ingestion_chunk_size: int = 1200
    ingestion_chunk_overlap: int = 160
    # OAuth/MCP protected-resource controls.  Duration values are caps; a
    # deployment may shorten but never exceed them.  The canonical resource is
    # always the public origin plus the fixed `/mcp` path.
    mcp_resource_path: str = "/mcp"
    oauth_authorization_code_seconds: int = 60
    oauth_access_token_seconds: int = 600
    oauth_refresh_absolute_seconds: int = 2592000
    oauth_refresh_rolling_seconds: int = 2592000
    service_credential_max_seconds: int = 7776000
    credential_rotation_overlap_seconds: int = 600
    mcp_legacy_alias_enabled: bool = False
    mcp_request_max_bytes: int = 4 * 1024 * 1024
    mcp_body_max_bytes: int = 8 * 1024 * 1024
    mcp_default_rate_limit: int = 300
    mcp_default_concurrency: int = 10
    oauth_authorize_rate_limit: int = 60
    oauth_token_rate_limit: int = 120

    @field_validator("public_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("public_origin must be an absolute HTTP(S) URL")
        if parsed.query or parsed.fragment:
            raise ValueError("public_origin cannot contain query or fragment")
        if parsed.path not in {"", "/"} or parsed.params:
            raise ValueError("public_origin must not contain a path")
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

    @field_validator("mcp_resource_path")
    @classmethod
    def validate_resource_path(cls, value: str) -> str:
        if value != "/mcp":
            raise ValueError("mcp_resource_path must be the canonical '/mcp' path")
        return value

    @field_validator(
        "oauth_authorization_code_seconds",
        "oauth_access_token_seconds",
        "oauth_refresh_absolute_seconds",
        "oauth_refresh_rolling_seconds",
        "service_credential_max_seconds",
        "credential_rotation_overlap_seconds",
    )
    @classmethod
    def validate_oauth_durations(cls, value: int) -> int:
        if value < 1:
            raise ValueError("OAuth durations must be positive")
        return value

    @field_validator("mcp_request_max_bytes", "mcp_body_max_bytes")
    @classmethod
    def validate_mcp_body_limits(cls, value: int) -> int:
        if value < 1 or value > 128 * 1024 * 1024:
            raise ValueError("MCP body limits must be between 1 and 134217728 bytes")
        return value

    @field_validator(
        "mcp_default_rate_limit",
        "mcp_default_concurrency",
        "oauth_authorize_rate_limit",
        "oauth_token_rate_limit",
    )
    @classmethod
    def validate_mcp_rate_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MCP rate and concurrency limits must be positive")
        return value

    @field_validator("max_body_bytes")
    @classmethod
    def validate_body_limit(cls, value: int) -> int:
        if value <= 0 or value > 512 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 and 536870912")
        return value

    @field_validator("storage_endpoint")
    @classmethod
    def validate_storage_endpoint(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("storage_endpoint must be an absolute HTTP(S) URL")
        return value.rstrip("/")

    @field_validator("storage_max_object_bytes", "ingestion_max_text_bytes")
    @classmethod
    def validate_storage_limits(cls, value: int) -> int:
        if value < 1 or value > 512 * 1024 * 1024:
            raise ValueError("storage and ingestion limits must be between 1 and 536870912")
        return value

    @field_validator("storage_presign_seconds", "storage_retention_seconds", "ingestion_max_chunks")
    @classmethod
    def validate_positive_limits(cls, value: int) -> int:
        if value < 1:
            raise ValueError("storage and ingestion limits must be positive")
        return value

    @field_validator("storage_connect_timeout_seconds", "storage_read_timeout_seconds")
    @classmethod
    def validate_storage_timeouts(cls, value: float) -> float:
        if value <= 0 or value > 300:
            raise ValueError("storage timeouts must be between 0 and 300 seconds")
        return value

    @field_validator("diagnostic_queue", "ingestion_queue", "worker_name")
    @classmethod
    def validate_runtime_identity(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", value):
            raise ValueError(
                "runtime identities must use lowercase ASCII letters, digits, '.', '_' or '-'"
            )
        return value

    @model_validator(mode="after")
    def validate_environment_constraints(self) -> Settings:
        storage_values = (
            self.storage_endpoint,
            self.storage_bucket,
            self.storage_access_key_id,
            self.storage_secret_access_key,
        )
        if any(value is not None for value in storage_values) and not all(storage_values):
            raise ValueError(
                "storage endpoint, bucket, and credentials must be configured together"
            )
        if self.ingestion_chunk_overlap >= self.ingestion_chunk_size:
            raise ValueError("ingestion_chunk_overlap must be less than ingestion_chunk_size")
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
        if not self.mcp_resource_path.startswith("/"):
            raise ValueError("mcp_resource_path must start with '/'")
        if self.oauth_authorization_code_seconds > 60:
            raise ValueError("oauth_authorization_code_seconds cannot exceed 60")
        if self.oauth_access_token_seconds > 600:
            raise ValueError("oauth_access_token_seconds cannot exceed 600")
        if self.oauth_refresh_absolute_seconds > 2592000:
            raise ValueError("oauth_refresh_absolute_seconds cannot exceed 2592000")
        if self.oauth_refresh_rolling_seconds > self.oauth_refresh_absolute_seconds:
            raise ValueError("oauth_refresh_rolling_seconds cannot exceed absolute lifetime")
        if self.service_credential_max_seconds > 7776000:
            raise ValueError("service_credential_max_seconds cannot exceed 7776000")
        if self.credential_rotation_overlap_seconds > 600:
            raise ValueError("credential_rotation_overlap_seconds cannot exceed 600")
        return self

    @property
    def task_url(self) -> str:
        return (self.task_database_url or self.database_url).get_secret_value()

    @property
    def mcp_resource_url(self) -> str:
        """Canonical public protected-resource URL (origin + resource path)."""
        return f"{self.public_origin}{self.mcp_resource_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
