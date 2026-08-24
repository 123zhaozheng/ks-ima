from email.message import EmailMessage

import pytest

from ima.config import Settings
from ima.infrastructure.mail import MailService


@pytest.mark.asyncio
async def test_smtp_fake_receives_clickable_reset_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[EmailMessage] = []

    async def fake_send(message: EmailMessage, **kwargs: object) -> None:
        captured.append(message)

    monkeypatch.setattr("aiosmtplib.send", fake_send)
    service = MailService(Settings(smtp_host="smtp.test", smtp_from="ima@test"))
    assert await service.send_password_reset("person@test", "opaque-token")
    assert captured
    assert "/auth/reset-password?token=opaque-token" in captured[0].get_content()
