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
}
PLAYWRIGHT_PROJECTS = {
    "chromium": ("CHROMIUM", "JBSWY3DPEHPK3PXP"),
    "mobile-chromium": ("MOBILE", "KRSXG5DSNFXGOIDB"),
}


def main() -> None:
    if os.environ.get("IMA_ENVIRONMENT") != "test":
        raise SystemExit("E2E identity seed is only allowed with IMA_ENVIRONMENT=test")
    suffixes = [suffix for suffix, _secret in PLAYWRIGHT_PROJECTS.values()]
    totp_secrets = [secret for _suffix, secret in PLAYWRIGHT_PROJECTS.values()]
    if len(set(suffixes)) != len(PLAYWRIGHT_PROJECTS) or len(set(totp_secrets)) != len(
        PLAYWRIGHT_PROJECTS
    ):
        raise ValueError("Playwright identity suffixes and TOTP secrets must be project-unique")
    now = datetime.now(UTC)
    with psycopg.connect(DB) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "TRUNCATE ima.audit_events, ima.recovery_codes, ima.totp_credentials, ima.sessions, ima.auth_tokens, ima.platform_role_assignments, ima.password_credentials, ima.users CASCADE"
            )
            accounts = [
                (key, email, name, role, key, None) for key, (email, name, role) in ACCOUNTS.items()
            ]
            for project_name in PLAYWRIGHT_PROJECTS:
                accounts.extend(
                    (
                        f"{project_name}-{kind}",
                        f"e2e-{kind}-{project_name}@example.com",
                        f"{kind.title()} User ({project_name})",
                        None,
                        kind,
                        project_name,
                    )
                    for kind in ("totp", "recovery", "invite", "oauth")
                )

            for key, email, name, role, kind, project_name in accounts:
                user_id = f"e2e-{key}-id"
                if len(user_id) > 32:
                    raise ValueError(f"E2E user ID exceeds 32 characters: {user_id}")
                if kind in {"totp", "recovery", "invite"} and project_name is None:
                    raise ValueError(f"E2E {kind} fixture requires a Playwright project")
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
                if kind != "invite":
                    cursor.execute(
                        "INSERT INTO ima.password_credentials(user_id,phc_hash,parameter_version,changed_at) VALUES (%s,%s,'e2e',%s)",
                        (user_id, hash_password(PASSWORD), now),
                    )
                if role:
                    cursor.execute(
                        "INSERT INTO ima.platform_role_assignments(user_id,role,created_at) VALUES (%s,%s,%s)",
                        (user_id, role, now),
                    )
                if kind in {"totp", "recovery"}:
                    project_suffix, project_totp_secret = PLAYWRIGHT_PROJECTS[project_name]
                    secret = project_totp_secret if kind == "totp" else pyotp.random_base32()
                    cursor.execute(
                        "INSERT INTO ima.totp_credentials(user_id,encrypted_secret,confirmed_at,created_at) VALUES (%s,%s,%s,%s)",
                        (user_id, encrypt_secret(secret, SECRET, user_id), now, now),
                    )
                    if kind == "recovery":
                        recovery_code = f"E2E-RECOVERY-CODE-{project_suffix}"
                        if len(recovery_code) > 32:
                            raise ValueError(
                                f"E2E recovery code exceeds 32 characters: {recovery_code}"
                            )
                        cursor.execute(
                            "INSERT INTO ima.recovery_codes(id,user_id,code_digest,created_at) VALUES (%s,%s,%s,%s)",
                            (uuid4(), user_id, digest(recovery_code, PEPPER), now),
                        )
                if kind == "invite":
                    project_suffix, _project_totp_secret = PLAYWRIGHT_PROJECTS[project_name]
                    invitation_token = f"E2E-INVITATION-TOKEN-{project_suffix}"
                    cursor.execute(
                        "INSERT INTO ima.auth_tokens(id,user_id,email,purpose,token_digest,expires_at,created_at) VALUES (%s,%s,%s,'invite',%s,%s,%s)",
                        (
                            uuid4(),
                            user_id,
                            email,
                            digest(invitation_token, PEPPER),
                            now + timedelta(hours=1),
                            now,
                        ),
                    )
                if kind == "oauth":
                    kb_id = f"e2e-oauth-{project_name}-kb"
                    if len(kb_id) > 32:
                        raise ValueError(
                            f"E2E OAuth knowledge base ID exceeds 32 characters: {kb_id}"
                        )
                    cursor.execute(
                        "INSERT INTO ima.knowledge_bases(id,name,is_active,created_by,created_at,updated_at) VALUES (%s,%s,true,%s,%s,%s)",
                        (kb_id, f"OAuth Knowledge Base ({project_name})", user_id, now, now),
                    )
                    cursor.execute(
                        "INSERT INTO ima.folders(id,kb_id,parent_id,name,normalized_name,is_root,created_by,created_at,updated_at) VALUES (%s,%s,NULL,%s,%s,true,%s,%s,%s)",
                        (
                            kb_id,
                            kb_id,
                            f"OAuth Knowledge Base ({project_name})",
                            f"oauth knowledge base ({project_name})",
                            user_id,
                            now,
                            now,
                        ),
                    )
                    cursor.execute(
                        "INSERT INTO ima.folder_closure(kb_id,ancestor_id,descendant_id,depth) VALUES (%s,%s,%s,0)",
                        (kb_id, kb_id, kb_id),
                    )
                    cursor.execute(
                        "INSERT INTO ima.kb_members(kb_id,user_id,role,state,joined_at) VALUES (%s,%s,'owner','active',%s)",
                        (kb_id, user_id, now),
                    )
            cursor.execute(
                "UPDATE ima.system_settings SET allow_registration=false,updated_at=%s WHERE id=true",
                (now,),
            )
        connection.commit()


if __name__ == "__main__":
    main()
