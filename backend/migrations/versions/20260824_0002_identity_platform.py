"""Local identity, platform administration, and compatibility projection."""

# Keep migration SQL visible as complete statements for security review.
# ruff: noqa: E501

from alembic import op

revision = "20260824_0002"
down_revision = "20260824_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
    CREATE TABLE IF NOT EXISTS ima.users (
      id varchar(32) PRIMARY KEY, email varchar(320) NOT NULL, normalized_email varchar(320) NOT NULL UNIQUE,
      display_name varchar(200) NOT NULL, image_url text, is_active boolean NOT NULL DEFAULT true,
      password_reset_required boolean NOT NULL DEFAULT false, security_stamp varchar(128) NOT NULL,
      disabled_at timestamptz, disabled_by varchar(32), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_ima_users_email ON ima.users (normalized_email);
    CREATE TABLE IF NOT EXISTS ima.password_credentials (
      user_id varchar(32) PRIMARY KEY REFERENCES ima.users(id) ON DELETE CASCADE, phc_hash text NOT NULL,
      parameter_version varchar(32) NOT NULL, changed_at timestamptz NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ima.sessions (
      id uuid PRIMARY KEY, user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
      token_digest varchar(128) NOT NULL UNIQUE, csrf_digest varchar(128) NOT NULL,
      security_stamp varchar(128) NOT NULL, created_at timestamptz NOT NULL, last_activity_at timestamptz NOT NULL,
      idle_expires_at timestamptz NOT NULL, absolute_expires_at timestamptz NOT NULL,
      recent_auth_at timestamptz NOT NULL, user_agent varchar(512), source_ip inet,
      revoked_at timestamptz, revoke_reason varchar(64)
    );
    CREATE INDEX IF NOT EXISTS ix_ima_sessions_user ON ima.sessions(user_id, revoked_at);
    CREATE TABLE IF NOT EXISTS ima.totp_credentials (
      user_id varchar(32) PRIMARY KEY REFERENCES ima.users(id) ON DELETE CASCADE, encrypted_secret bytea NOT NULL,
      key_version integer NOT NULL DEFAULT 1, confirmed_at timestamptz, created_at timestamptz NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ima.recovery_codes (
      id uuid PRIMARY KEY, user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
      code_digest varchar(128) NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_ima_recovery_user ON ima.recovery_codes(user_id, used_at);
    CREATE TABLE IF NOT EXISTS ima.auth_tokens (
      id uuid PRIMARY KEY, user_id varchar(32) REFERENCES ima.users(id) ON DELETE CASCADE,
      email varchar(320) NOT NULL, purpose varchar(32) NOT NULL, token_digest varchar(128) NOT NULL UNIQUE,
      expires_at timestamptz NOT NULL, used_at timestamptz, created_at timestamptz NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ima.platform_role_assignments (
      user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE, role varchar(32) NOT NULL,
      grantor_id varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL,
      PRIMARY KEY(user_id, role), CONSTRAINT platform_role_valid CHECK(role IN ('super_admin','platform_admin','security_auditor'))
    );
    CREATE TABLE IF NOT EXISTS ima.auth_rate_limits (
      bucket_digest varchar(128) NOT NULL, action varchar(64) NOT NULL, window_start timestamptz NOT NULL,
      attempts integer NOT NULL DEFAULT 0, blocked_until timestamptz, PRIMARY KEY(bucket_digest, action, window_start)
    );
    CREATE TABLE IF NOT EXISTS ima.system_settings (
      id boolean PRIMARY KEY DEFAULT true CHECK(id), allow_registration boolean NOT NULL DEFAULT false,
      smtp_enabled boolean NOT NULL DEFAULT false, session_idle_seconds integer NOT NULL DEFAULT 86400,
      session_absolute_seconds integer NOT NULL DEFAULT 2592000, recent_auth_seconds integer NOT NULL DEFAULT 900,
      updated_at timestamptz NOT NULL, updated_by varchar(32) REFERENCES ima.users(id)
    );
    CREATE TABLE IF NOT EXISTS ima.workspaces (
      id varchar(32) PRIMARY KEY, name varchar(200) NOT NULL, is_active boolean NOT NULL DEFAULT true,
      archived_at timestamptz, created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_ima_workspaces_name ON ima.workspaces(lower(name));
    CREATE TABLE IF NOT EXISTS ima.audit_events (
      id bigserial PRIMARY KEY, actor_id varchar(32) REFERENCES ima.users(id), action varchar(96) NOT NULL,
      target_type varchar(64), target_id varchar(128), result varchar(32) NOT NULL, reason_code varchar(64),
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb, correlation_id varchar(64), source_ip inet, created_at timestamptz NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_ima_audit_created ON ima.audit_events(created_at DESC);
    CREATE TABLE IF NOT EXISTS ima.legacy_identity_projection (
      user_id varchar(32) PRIMARY KEY REFERENCES ima.users(id) ON DELETE CASCADE, status varchar(32) NOT NULL,
      last_error text, migrated_at timestamptz, updated_at timestamptz NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ima.legacy_identity_migration (
      source_kind varchar(32) NOT NULL, source_id varchar(128) NOT NULL,
      status varchar(32) NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0,
      last_error varchar(128), source_fingerprint varchar(128),
      processed_at timestamptz, updated_at timestamptz NOT NULL,
      PRIMARY KEY(source_kind, source_id)
    );
    INSERT INTO ima.system_settings(id, updated_at) VALUES(true, now()) ON CONFLICT(id) DO NOTHING;
    """)


def downgrade() -> None:
    for table in (
        "legacy_identity_projection",
        "legacy_identity_migration",
        "audit_events",
        "workspaces",
        "system_settings",
        "auth_rate_limits",
        "platform_role_assignments",
        "auth_tokens",
        "recovery_codes",
        "totp_credentials",
        "sessions",
        "password_credentials",
        "users",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
