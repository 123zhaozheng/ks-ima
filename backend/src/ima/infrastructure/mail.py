"""Optional SMTP adapter. Disabled mail is an explicit operational state."""

from __future__ import annotations

from email.message import EmailMessage

import aiosmtplib

from ima.config import Settings


class MailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @property
    def enabled(self) -> bool:
        return bool(self.settings.smtp_host and self.settings.smtp_from)

    async def send_password_reset(self, email: str, token: str) -> bool:
        if not self.enabled:
            return False
        message = EmailMessage()
        message["From"] = self.settings.smtp_from or ""
        message["To"] = email
        message["Subject"] = "Intranet IMA password reset"
        message.set_content(
            f"Reset your password: {self.settings.public_origin}/auth/reset-password?"
            f"token={token}\n"
            "This link expires in one hour and can be used once."
        )
        await aiosmtplib.send(
            message,
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_username,
            password=self.settings.smtp_password.get_secret_value()
            if self.settings.smtp_password
            else None,
            start_tls=self.settings.smtp_port != 465,
            use_tls=self.settings.smtp_port == 465,
        )
        return True

    async def send_invitation(self, email: str, token: str) -> bool:
        if not self.enabled:
            return False
        message = EmailMessage()
        message["From"] = self.settings.smtp_from or ""
        message["To"] = email
        message["Subject"] = "Your Intranet IMA invitation"
        message.set_content(
            f"Accept your invitation: {self.settings.public_origin}/api/v1/"
            f"workspace-invitations/{token}/accept\n"
            "The invitation expires in two days."
        )
        await aiosmtplib.send(
            message,
            hostname=self.settings.smtp_host,
            port=self.settings.smtp_port,
            username=self.settings.smtp_username,
            password=self.settings.smtp_password.get_secret_value()
            if self.settings.smtp_password
            else None,
            start_tls=self.settings.smtp_port != 465,
            use_tls=self.settings.smtp_port == 465,
        )
        return True
