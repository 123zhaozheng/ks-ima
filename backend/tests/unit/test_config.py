import pytest
from pydantic import SecretStr, ValidationError

from ima.config import Settings


def test_secret_is_not_in_settings_repr() -> None:
    settings = Settings(database_url=SecretStr("postgresql+asyncpg://user:password@db/app"))
    assert "password" not in repr(settings)
    assert settings.database_url.get_secret_value().endswith("/app")


def test_wildcard_cors_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(cors_origins=("*",))


def test_proxy_networks_are_validated() -> None:
    with pytest.raises(ValidationError):
        Settings(trusted_proxies=("not-a-network",))


def test_production_requires_https_and_explicit_origins() -> None:
    with pytest.raises(ValidationError):
        Settings(environment="production")


def test_legacy_unprefixed_database_url_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgres://legacy-value")
    settings = Settings(environment="test")
    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg://")


def test_structured_environment_values_accept_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMA_CORS_ORIGINS", "http://localhost:8080")
    monkeypatch.setenv("IMA_TRUSTED_PROXIES", "127.0.0.1,172.16.0.0/12")
    settings = Settings(environment="test")
    assert settings.cors_origins == ("http://localhost:8080",)
    assert settings.trusted_proxies == ("127.0.0.1", "172.16.0.0/12")


def test_runtime_identity_is_validated() -> None:
    settings = Settings(
        environment="test",
        diagnostic_queue="diagnostic.integration",
        worker_name="worker.integration",
    )
    assert settings.diagnostic_queue == "diagnostic.integration"
    assert settings.worker_name == "worker.integration"
    with pytest.raises(ValidationError):
        Settings(environment="test", worker_name="Worker With Spaces")
