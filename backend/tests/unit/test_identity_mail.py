import pytest

from ima.config import Settings
from ima.infrastructure.mail import MailService


@pytest.mark.asyncio
async def test_smtp_disabled_is_explicit() -> None:
    service = MailService(Settings(smtp_host=None, smtp_from=None))
    assert service.enabled is False
    assert await service.send_password_reset("user@example.test", "opaque-token") is False
    assert await service.send_invitation("user@example.test", "opaque-token") is False
