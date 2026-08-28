"""OAuth clients, human grants, codes/tokens, and service-principal credentials."""

# SQL statements remain readable as complete migration blocks.
# ruff: noqa: E501

from alembic import op

revision = "20260826_0008"
down_revision = "20260826_0007"
branch_labels = None
depends_on = None

# Canonical MCP scope values enforced by CHECK constraints.  Keeping the list in
# one place lets guards stay in sync with ima.application.mcp_contracts.McpScope.
_MCP_SCOPES = (
    "mcp:workspaces:read",
    "mcp:knowledge:read",
    "mcp:knowledge:search",
    "mcp:knowledge:ask",
    "mcp:knowledge:write",
)
_SCOPE_LITERAL = ",".join(f"'{scope}'" for scope in _MCP_SCOPES)


def upgrade() -> None:
    op.execute(
        f"""
        CREATE TABLE ima.mcp_clients (
          id uuid PRIMARY KEY,
          client_id varchar(128) NOT NULL UNIQUE,
          client_name varchar(200) NOT NULL,
          client_type varchar(16) NOT NULL CHECK(client_type IN ('public','confidential')),
          token_endpoint_auth_method varchar(32) NOT NULL DEFAULT 'none' CHECK(token_endpoint_auth_method IN ('none','client_secret_basic')),
          client_secret_digest varchar(128),
          application_type varchar(16) NOT NULL CHECK(application_type IN ('native','web')),
          canonical_resource varchar(512) NOT NULL,
          is_enabled boolean NOT NULL DEFAULT true,
          disabled_at timestamptz,
          disabled_reason varchar(64),
          created_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL
        );
        CREATE INDEX ix_mcp_clients_enabled ON ima.mcp_clients(is_enabled, client_id);

        CREATE TABLE ima.mcp_client_redirects (
          client_id uuid NOT NULL REFERENCES ima.mcp_clients(id) ON DELETE CASCADE,
          redirect_uri varchar(512) NOT NULL,
          is_loopback boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL,
          PRIMARY KEY(client_id, redirect_uri)
        );
        CREATE INDEX ix_mcp_client_redirects_loopback ON ima.mcp_client_redirects(client_id, is_loopback);

        CREATE TABLE ima.mcp_grants (
          id uuid PRIMARY KEY,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE RESTRICT,
          client_id uuid NOT NULL REFERENCES ima.mcp_clients(id) ON DELETE RESTRICT,
          canonical_resource varchar(512) NOT NULL,
          workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE RESTRICT,
          folder_root_id varchar(32),
          folder_root_key varchar(32) GENERATED ALWAYS AS (COALESCE(folder_root_id,'')) STORED,
          scopes text[] NOT NULL CHECK(cardinality(scopes) > 0 AND scopes <@ ARRAY[{_SCOPE_LITERAL}]::text[]),
          state varchar(16) NOT NULL DEFAULT 'active' CHECK(state IN ('active','revoked')),
          revocation_epoch integer NOT NULL DEFAULT 0 CHECK(revocation_epoch >= 0),
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL,
          last_used_at timestamptz,
          revoked_at timestamptz,
          revoke_reason varchar(64),
          consent_granted_by varchar(32) REFERENCES ima.users(id),
          FOREIGN KEY(workspace_id,folder_root_id) REFERENCES ima.folders(workspace_id,id) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX ux_mcp_grants_active_boundary
          ON ima.mcp_grants(user_id,client_id,canonical_resource,workspace_id,folder_root_key) WHERE state='active';
        CREATE INDEX ix_mcp_grants_user ON ima.mcp_grants(user_id,state,expires_at);

        CREATE TABLE ima.mcp_authorization_codes (
          id uuid PRIMARY KEY,
          code_digest varchar(128) NOT NULL UNIQUE,
          grant_id uuid NOT NULL REFERENCES ima.mcp_grants(id) ON DELETE RESTRICT,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE RESTRICT,
          client_id uuid NOT NULL REFERENCES ima.mcp_clients(id) ON DELETE RESTRICT,
          redirect_uri varchar(512) NOT NULL,
          canonical_resource varchar(512) NOT NULL,
          workspace_id varchar(32) NOT NULL,
          folder_root_id varchar(32),
          scopes text[] NOT NULL CHECK(cardinality(scopes) > 0 AND scopes <@ ARRAY[{_SCOPE_LITERAL}]::text[]),
          code_challenge varchar(128) NOT NULL,
          code_challenge_method varchar(16) NOT NULL DEFAULT 'S256' CHECK(code_challenge_method IN ('S256')),
          security_stamp varchar(128) NOT NULL,
          state varchar(128) NOT NULL,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          created_at timestamptz NOT NULL,
          FOREIGN KEY(client_id,redirect_uri)
            REFERENCES ima.mcp_client_redirects(client_id,redirect_uri) ON DELETE RESTRICT
        );
        CREATE INDEX ix_mcp_auth_codes_expiry ON ima.mcp_authorization_codes(expires_at,used_at);

        CREATE TABLE ima.mcp_refresh_families (
          id uuid PRIMARY KEY,
          grant_id uuid NOT NULL REFERENCES ima.mcp_grants(id) ON DELETE RESTRICT,
          created_at timestamptz NOT NULL,
          rotated_generation integer NOT NULL DEFAULT 0 CHECK(rotated_generation >= 0),
          absolute_expires_at timestamptz NOT NULL,
          security_stamp varchar(128) NOT NULL,
          revoked_at timestamptz,
          revoke_reason varchar(64),
          replay_detected_at timestamptz
        );
        ALTER TABLE ima.mcp_refresh_families ADD CONSTRAINT ux_mcp_refresh_family_grant UNIQUE(id,grant_id);
        CREATE INDEX ix_mcp_refresh_families_grant ON ima.mcp_refresh_families(grant_id,revoked_at);

        CREATE TABLE ima.mcp_refresh_tokens (
          id uuid PRIMARY KEY,
          token_digest varchar(128) NOT NULL UNIQUE,
          family_id uuid NOT NULL REFERENCES ima.mcp_refresh_families(id) ON DELETE RESTRICT,
          grant_id uuid NOT NULL REFERENCES ima.mcp_grants(id) ON DELETE RESTRICT,
          client_id uuid NOT NULL REFERENCES ima.mcp_clients(id) ON DELETE RESTRICT,
          canonical_resource varchar(512) NOT NULL,
          workspace_id varchar(32) NOT NULL,
          folder_root_id varchar(32),
          scopes text[] NOT NULL CHECK(cardinality(scopes) > 0 AND scopes <@ ARRAY[{_SCOPE_LITERAL}]::text[]),
          issued_at timestamptz NOT NULL,
          expires_at timestamptz NOT NULL,
          replaced_at timestamptz,
          replaced_by uuid UNIQUE REFERENCES ima.mcp_refresh_tokens(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
          revoked_at timestamptz,
          revoke_reason varchar(64),
          CHECK (replaced_at IS NULL OR replaced_by IS NOT NULL),
          FOREIGN KEY(family_id,grant_id)
            REFERENCES ima.mcp_refresh_families(id,grant_id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_mcp_refresh_tokens_family ON ima.mcp_refresh_tokens(family_id,replaced_at);

        CREATE TABLE ima.mcp_service_principals (
          id uuid PRIMARY KEY,
          workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE RESTRICT,
          folder_root_id varchar(32),
          display_name varchar(200) NOT NULL,
          purpose varchar(500) NOT NULL,
          owner_user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE RESTRICT,
          scopes text[] NOT NULL CHECK(cardinality(scopes) > 0 AND scopes <@ ARRAY[{_SCOPE_LITERAL}]::text[]),
          state varchar(16) NOT NULL DEFAULT 'active' CHECK(state IN ('active','disabled','revoked')),
          created_by varchar(32) REFERENCES ima.users(id),
          expires_at timestamptz NOT NULL,
          cidr_allowlist text[] DEFAULT NULL,
          rate_limit integer NOT NULL DEFAULT 300 CHECK(rate_limit > 0),
          concurrency_limit integer NOT NULL DEFAULT 10 CHECK(concurrency_limit > 0),
          created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL,
          revoked_at timestamptz,
          revoke_reason varchar(64),
          FOREIGN KEY(workspace_id,folder_root_id) REFERENCES ima.folders(workspace_id,id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_mcp_service_principals_workspace ON ima.mcp_service_principals(workspace_id,state);

        CREATE TABLE ima.mcp_credentials (
          id uuid PRIMARY KEY,
          principal_id uuid NOT NULL REFERENCES ima.mcp_service_principals(id) ON DELETE CASCADE,
          credential_id varchar(32) NOT NULL UNIQUE,
          digest varchar(128) NOT NULL UNIQUE,
          secret_prefix varchar(32) NOT NULL,
          created_at timestamptz NOT NULL,
          created_by varchar(32) REFERENCES ima.users(id),
          expires_at timestamptz NOT NULL,
          overlap_expires_at timestamptz CHECK(overlap_expires_at IS NULL OR overlap_expires_at <= expires_at),
          revoked_at timestamptz,
          revoke_reason varchar(64),
          last_used_at timestamptz,
          replaced_by uuid REFERENCES ima.mcp_credentials(id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED,
          CHECK (expires_at > created_at)
        );
        CREATE INDEX ix_mcp_credentials_principal ON ima.mcp_credentials(principal_id,expires_at);

        CREATE TABLE ima.mcp_access_tokens (
          id uuid PRIMARY KEY,
          token_digest varchar(128) NOT NULL UNIQUE,
          grant_id uuid REFERENCES ima.mcp_grants(id) ON DELETE RESTRICT,
          principal_id uuid REFERENCES ima.mcp_service_principals(id) ON DELETE RESTRICT,
          client_id uuid REFERENCES ima.mcp_clients(id) ON DELETE RESTRICT,
          canonical_resource varchar(512) NOT NULL,
          workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE RESTRICT,
          folder_root_id varchar(32),
          scopes text[] NOT NULL CHECK(cardinality(scopes) > 0 AND scopes <@ ARRAY[{_SCOPE_LITERAL}]::text[]),
          security_stamp varchar(128),
          expires_at timestamptz NOT NULL,
          created_at timestamptz NOT NULL,
          revoked_at timestamptz,
          revoke_reason varchar(64),
          last_used_at timestamptz,
          CHECK (
            (grant_id IS NOT NULL AND principal_id IS NULL AND client_id IS NOT NULL AND security_stamp IS NOT NULL)
            OR
            (grant_id IS NULL AND principal_id IS NOT NULL AND client_id IS NULL AND security_stamp IS NULL)
          )
        );
        CREATE INDEX ix_mcp_access_tokens_expiry ON ima.mcp_access_tokens(expires_at,revoked_at);

        CREATE TABLE ima.mcp_rate_buckets (
          bucket_digest varchar(128) NOT NULL,
          bucket_kind varchar(32) NOT NULL CHECK(bucket_kind IN ('token','tool','service','authorize','source')),
          action varchar(64) NOT NULL,
          window_start timestamptz NOT NULL,
          attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
          blocked_until timestamptz,
          PRIMARY KEY(bucket_digest, bucket_kind, action, window_start)
        );

        CREATE TABLE ima.mcp_concurrency_leases (
          id uuid PRIMARY KEY,
          bucket_digest varchar(128) NOT NULL,
          request_digest varchar(128) NOT NULL UNIQUE,
          token_id uuid NOT NULL REFERENCES ima.mcp_access_tokens(id) ON DELETE CASCADE,
          principal_id uuid REFERENCES ima.mcp_service_principals(id) ON DELETE CASCADE,
          source_digest varchar(128) NOT NULL,
          created_at timestamptz NOT NULL,
          expires_at timestamptz NOT NULL CHECK(expires_at > created_at)
        );
        CREATE INDEX ix_mcp_concurrency_bucket_expiry
          ON ima.mcp_concurrency_leases(bucket_digest,expires_at);
        CREATE INDEX ix_mcp_concurrency_source_expiry
          ON ima.mcp_concurrency_leases(source_digest,expires_at);
        """
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM ima.mcp_credentials LIMIT 1)
             OR EXISTS (SELECT 1 FROM ima.mcp_grants LIMIT 1)
          THEN RAISE EXCEPTION 'oauth/mcp downgrade requires an explicit verified snapshot'; END IF;
        END $$;"""
    )
    for table in (
        "mcp_concurrency_leases",
        "mcp_rate_buckets",
        "mcp_access_tokens",
        "mcp_credentials",
        "mcp_service_principals",
        "mcp_refresh_tokens",
        "mcp_refresh_families",
        "mcp_authorization_codes",
        "mcp_grants",
        "mcp_client_redirects",
        "mcp_clients",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
