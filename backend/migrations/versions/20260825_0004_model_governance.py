"""Central model governance, encrypted gateway credentials and assignments."""

# Keep migration SQL as complete statements for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260825_0004"
down_revision = "20260825_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ima.model_gateway_secrets (
          id uuid PRIMARY KEY,
          key_version varchar(32) NOT NULL,
          nonce bytea NOT NULL,
          ciphertext bytea NOT NULL,
          fingerprint varchar(32) NOT NULL,
          created_at timestamptz NOT NULL,
          rotated_at timestamptz,
          rotated_by varchar(32) REFERENCES ima.users(id)
        );
        CREATE TABLE IF NOT EXISTS ima.model_gateways (
          id uuid PRIMARY KEY,
          name varchar(120) NOT NULL UNIQUE,
          normalized_base_url varchar(2048) NOT NULL,
          enabled boolean NOT NULL DEFAULT false,
          allowed_capabilities varchar(32)[] NOT NULL,
          tls_mode varchar(16) NOT NULL CHECK(tls_mode IN ('required','private_http')),
          insecure_private boolean NOT NULL DEFAULT false,
          custom_ca_ref varchar(512),
          connect_timeout_ms integer NOT NULL CHECK(connect_timeout_ms BETWEEN 100 AND 300000),
          read_timeout_ms integer NOT NULL CHECK(read_timeout_ms BETWEEN 100 AND 300000),
          write_timeout_ms integer NOT NULL CHECK(write_timeout_ms BETWEEN 100 AND 300000),
          pool_timeout_ms integer NOT NULL CHECK(pool_timeout_ms BETWEEN 100 AND 300000),
          max_response_bytes integer NOT NULL CHECK(max_response_bytes BETWEEN 1024 AND 134217728),
          allowed_hosts varchar(255)[] NOT NULL DEFAULT '{}',
          allowed_cidrs varchar(64)[] NOT NULL DEFAULT '{}',
          secret_id uuid REFERENCES ima.model_gateway_secrets(id) ON DELETE RESTRICT,
          version integer NOT NULL DEFAULT 1 CHECK(version > 0),
          created_by varchar(32) REFERENCES ima.users(id),
          updated_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_model_gateways_enabled ON ima.model_gateways(enabled);
        CREATE TABLE IF NOT EXISTS ima.model_gateway_health (
          gateway_id uuid NOT NULL REFERENCES ima.model_gateways(id) ON DELETE CASCADE,
          capability varchar(32) NOT NULL CHECK(capability IN ('chat','embedding','rerank')),
          state varchar(16) NOT NULL CHECK(state IN ('unknown','healthy','degraded','unavailable')),
          reason_code varchar(64), latency_ms integer, checked_at timestamptz,
          next_check_at timestamptz, consecutive_failures integer NOT NULL DEFAULT 0,
          PRIMARY KEY(gateway_id,capability)
        );
        CREATE TABLE IF NOT EXISTS ima.governed_models (
          id uuid PRIMARY KEY,
          gateway_id uuid NOT NULL REFERENCES ima.model_gateways(id) ON DELETE RESTRICT,
          remote_name varchar(255) NOT NULL,
          capability varchar(32) NOT NULL CHECK(capability IN ('chat','embedding','rerank')),
          business_label varchar(200) NOT NULL,
          enabled boolean NOT NULL DEFAULT false,
          validated boolean NOT NULL DEFAULT false,
          validation_digest varchar(128),
          validated_at timestamptz,
          context_limit integer CHECK(context_limit IS NULL OR context_limit BETWEEN 1 AND 2097152),
          output_limit integer CHECK(output_limit IS NULL OR output_limit BETWEEN 1 AND 524288),
          embedding_dimension integer CHECK(embedding_dimension IS NULL OR embedding_dimension BETWEEN 1 AND 65536),
          max_documents integer CHECK(max_documents IS NULL OR max_documents BETWEEN 1 AND 1000),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0),
          created_by varchar(32) REFERENCES ima.users(id),
          updated_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL,
          UNIQUE(gateway_id,remote_name,capability)
        );
        CREATE INDEX IF NOT EXISTS ix_governed_models_capability ON ima.governed_models(capability,enabled);
        CREATE TABLE IF NOT EXISTS ima.capability_profiles (
          id uuid PRIMARY KEY,
          workflow varchar(32) NOT NULL CHECK(workflow IN ('grounded_ask','title_generation','summarization','embedding','reranking')),
          business_alias varchar(200) NOT NULL,
          description varchar(1000) NOT NULL,
          lifecycle varchar(16) NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','disabled','archived')),
          current_version integer NOT NULL DEFAULT 0 CHECK(current_version >= 0),
          created_by varchar(32) REFERENCES ima.users(id), updated_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_capability_profiles_workflow_alias ON ima.capability_profiles(workflow,lower(business_alias));
        CREATE TABLE IF NOT EXISTS ima.capability_profile_versions (
          profile_id uuid NOT NULL REFERENCES ima.capability_profiles(id) ON DELETE RESTRICT,
          version integer NOT NULL CHECK(version > 0),
          state varchar(16) NOT NULL CHECK(state IN ('draft','published','disabled')),
          config jsonb NOT NULL,
          config_digest varchar(128) NOT NULL,
          draft_version integer NOT NULL DEFAULT 1 CHECK(draft_version > 0),
          published_at timestamptz, published_by varchar(32) REFERENCES ima.users(id),
          disabled_at timestamptz, disabled_by varchar(32) REFERENCES ima.users(id),
          created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL,
          updated_at timestamptz NOT NULL,
          PRIMARY KEY(profile_id,version)
        );
        CREATE INDEX IF NOT EXISTS ix_profile_versions_state ON ima.capability_profile_versions(profile_id,state);
        CREATE OR REPLACE FUNCTION ima.reject_published_profile_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.state = 'published' AND (NEW.config IS DISTINCT FROM OLD.config OR NEW.config_digest IS DISTINCT FROM OLD.config_digest OR NEW.published_at IS DISTINCT FROM OLD.published_at OR NEW.published_by IS DISTINCT FROM OLD.published_by) THEN
            RAISE EXCEPTION 'published capability profile versions are immutable';
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER IF EXISTS trg_published_profile_immutable ON ima.capability_profile_versions;
        CREATE TRIGGER trg_published_profile_immutable BEFORE UPDATE ON ima.capability_profile_versions FOR EACH ROW EXECUTE FUNCTION ima.reject_published_profile_rewrite();
        CREATE TABLE IF NOT EXISTS ima.kb_profile_assignments (
          kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          workflow varchar(32) NOT NULL CHECK(workflow IN ('grounded_ask','title_generation','summarization','embedding','reranking')),
          profile_id uuid NOT NULL, profile_version integer NOT NULL,
          version integer NOT NULL DEFAULT 1 CHECK(version > 0),
          availability varchar(16) NOT NULL DEFAULT 'unavailable' CHECK(availability IN ('available','degraded','unavailable')),
          availability_reason varchar(64), assigned_by varchar(32) REFERENCES ima.users(id), assigned_at timestamptz NOT NULL,
          PRIMARY KEY(kb_id,workflow),
          FOREIGN KEY(profile_id,profile_version) REFERENCES ima.capability_profile_versions(profile_id,version) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS ix_profile_assignments_profile ON ima.kb_profile_assignments(profile_id,profile_version);
        CREATE TABLE IF NOT EXISTS ima.model_dependency_index (
          id uuid PRIMARY KEY,
          dependency_kind varchar(32) NOT NULL CHECK(dependency_kind IN ('target_index','legacy_index','job','answer')),
          kb_id varchar(32) REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          source_id varchar(255) NOT NULL,
          model_id uuid REFERENCES ima.governed_models(id) ON DELETE RESTRICT,
          profile_id uuid, profile_version integer, dimension integer,
          active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(dependency_kind,kb_id,source_id),
          FOREIGN KEY(profile_id,profile_version)
            REFERENCES ima.capability_profile_versions(profile_id,version)
            ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS ix_model_dependency_model ON ima.model_dependency_index(model_id,active,dependency_kind);
        CREATE TABLE IF NOT EXISTS ima.legacy_model_governance_migration (
          source_kind varchar(64) NOT NULL, source_id varchar(255) NOT NULL,
          source_fingerprint varchar(128) NOT NULL, mapped_target_id uuid,
          status varchar(16) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed','review')),
          attempts integer NOT NULL DEFAULT 0, last_error varchar(128), processed_at timestamptz,
          updated_at timestamptz NOT NULL, PRIMARY KEY(source_kind,source_id)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ima.model_gateways LIMIT 1)
           OR EXISTS (SELECT 1 FROM ima.capability_profile_versions LIMIT 1)
           OR EXISTS (SELECT 1 FROM ima.kb_profile_assignments LIMIT 1)
        THEN RAISE EXCEPTION 'model governance downgrade requires an explicit verified snapshot'; END IF;
        END $$;"""
    )
    for table in (
        "legacy_model_governance_migration",
        "model_dependency_index",
        "kb_profile_assignments",
        "capability_profile_versions",
        "capability_profiles",
        "governed_models",
        "model_gateway_health",
        "model_gateways",
        "model_gateway_secrets",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
    op.execute("DROP FUNCTION IF EXISTS ima.reject_published_profile_rewrite()")
