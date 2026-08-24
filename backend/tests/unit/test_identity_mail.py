import pytest

from ima.config import Settings
from ima.infrastructure.mail import MailService


@pytest.mark.asyncio
async def test_smtp_disabled_is_explicit() -> None:
    service = MailService(Settings(smtp_host=None, smtp_from=None))
    assert service.enabled is False
    assert await service.send_password_reset("user@example.test", "opaque-token") is False
    assert await service.send_invitation("user@example.test", "opaque-token") is False


@pytest.mark.asyncio
async def test_smtp_invitation_uses_workspace_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[str] = []

    async def send(message: object, **_: object) -> None:
        captured.append(str(message))

    monkeypatch.setattr("ima.infrastructure.mail.aiosmtplib.send", send)
    service = MailService(
        Settings(
            smtp_host="smtp.example.test",
            smtp_from="ima@example.test",
            smtp_port=587,
            public_origin="https://ima.example.test",
        )
    )
    assert await service.send_invitation("user@example.test", "opaque-token") is True
    assert "/api/v1/workspace-invitations/opaque-token/accept" in captured[0].replace("=\n", "")
