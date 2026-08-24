"""Seed deterministic identity accounts for the isolated Playwright database."""

# Keep deterministic fixture SQL visible as complete statements.
# ruff: noqa: E501

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg
import pyotp

from ima.application.identity import new_legacy_id
from ima.infrastructure.auth.security import digest, encrypt_secret, hash_password

PASSWORD = "E2E-password-123"
DB = (
    os.environ["IMA_DATABASE_URL"]
    .replace("postgresql+asyncpg://", "postgresql://")
    .replace("postgresql+psycopg://", "postgresql://")
)
SECRET = os.environ.get("IMA_TOTP_ENCRYPTION_KEY", "e2e-totp-key")
PEPPER = os.environ.get("IMA_TOKEN_PEPPER", "e2e-token-pepper")

ACCOUNTS = {
    "ordinary": ("e2e-ordinary@example.com", "Ordinary User", None),
    "super": ("e2e-super@example.com", "Super Admin", "super_admin"),
    "platform": ("e2e-platform@example.com", "Platform Admin", "platform_admin"),
    "auditor": ("e2e-auditor@example.com", "Security Auditor", "security_auditor"),
    "disabled": ("e2e-disabled@example.com", "Disabled User", None),
    "totp": ("e2e-totp@example.com", "TOTP User", None),
    "recovery": ("e2e-recovery@example.com", "Recovery User", None),
    "invite": ("e2e-invite@example.com", "Invited User", None),
}

INVITATION_TOKEN = "E2E-INVITATION-TOKEN-0000000001"


def main() -> None:
    if os.environ.get("IMA_ENVIRONMENT") != "test":
        raise SystemExit("E2E identity seed is only allowed with IMA_ENVIRONMENT=test")
    now = datetime.now(UTC)
    with psycopg.connect(DB) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE ima.audit_events, ima.recovery_codes, ima.totp_credentials, ima.sessions, ima.auth_tokens, ima.platform_role_assignments, ima.password_credentials, ima.users CASCADE"
            )
            for key, (email, name, role) in ACCOUNTS.items():
                user_id = f"e2e-{key}-id"[:32]
                cursor.execute(
                    "INSERT INTO ima.users(id,email,normalized_email,display_name,is_active,password_reset_required,security_stamp,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,false,%s,%s,%s)",
                    (
                        user_id,
                        email,
                        email.casefold(),
                        name,
                        key != "disabled",
                        new_legacy_id(),
                        now,
                        now,
                    ),
                )
                if key != "invite":
                    cursor.execute(
                        "INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (%s,%s,'e2e',%s)",
                        (user_id, hash_password(PASSWORD), now),
                    )
                if role:
                    cursor.execute(
                        "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (%s,%s,%s)",
                        (user_id, role, now),
                    )
                if key in {"totp", "recovery"}:
                    secret = "JBSWY3DPEHPK3PXP" if key == "totp" else pyotp.random_base32()
                    cursor.execute(
                        "INSERT INTO ima.totp_credentials(user_id,encrypted_secret,confirmed_at,created_at) VALUES (%s,%s,%s,%s)",
                        (user_id, encrypt_secret(secret, SECRET, user_id), now, now),
                    )
                    if key == "recovery":
                        cursor.execute(
                            "INSERT INTO ima.recovery_codes(id,user_id,code_digest,created_at) VALUES (%s,%s,%s,%s)",
                            (uuid4(), user_id, digest("E2E-RECOVERY-CODE", PEPPER), now),
                        )
                if key == "invite":
                    cursor.execute(
                        "INSERT INTO ima.auth_tokens(id,user_id,email,purpose,token_digest,expires_at,created_at) VALUES (%s,%s,%s,'invite',%s,%s,%s)",
                        (
                            uuid4(),
                            user_id,
                            email,
                            digest(INVITATION_TOKEN, PEPPER),
                            now + timedelta(hours=1),
                            now,
                        ),
                    )
            cursor.execute(
                "UPDATE ima.system_settings SET allow_registration=false,updated_at=%s WHERE id=true",
                (now,),
            )
        connection.commit()


if __name__ == "__main__":
    main()
