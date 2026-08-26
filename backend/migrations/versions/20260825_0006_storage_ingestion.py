"""Object storage and durable ingestion relations."""

# SQL statements remain readable as complete migration blocks.
# ruff: noqa: E501

from alembic import op

revision = "20260825_0006"
down_revision = "20260825_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ima.document_file_versions (
          document_id uuid NOT NULL REFERENCES ima.documents(id) ON DELETE RESTRICT,
          version integer NOT NULL CHECK(version > 0), workspace_id varchar(32) NOT NULL,
          generation integer NOT NULL DEFAULT 1 CHECK(generation > 0), object_state varchar(16) NOT NULL CHECK(object_state IN ('pending','verified','failed','orphaned')),
          object_key varchar(1024) NOT NULL, checksum_algorithm varchar(16) NOT NULL DEFAULT 'sha256' CHECK(checksum_algorithm='sha256'), checksum varchar(64) NOT NULL CHECK(checksum ~ '^[0-9a-f]{64}$'),
          size_bytes bigint NOT NULL CHECK(size_bytes >= 0), mime_type varchar(255) NOT NULL, original_filename varchar(255) NOT NULL,
          source_fingerprint varchar(128), created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, verified_at timestamptz,
          PRIMARY KEY(document_id, version), UNIQUE(workspace_id, object_key),
          FOREIGN KEY(workspace_id, document_id) REFERENCES ima.documents(workspace_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_document_file_versions_object ON ima.document_file_versions(workspace_id, checksum, size_bytes, mime_type) WHERE object_state='verified';
        CREATE TABLE ima.document_derived_text (
          document_id uuid NOT NULL, version integer NOT NULL, generation integer NOT NULL, parser_name varchar(32) NOT NULL, parser_version varchar(32) NOT NULL,
          source_checksum varchar(64) NOT NULL, text_digest varchar(64) NOT NULL, text_content text NOT NULL, status varchar(16) NOT NULL CHECK(status IN ('ready','failed','unsupported')),
          error_code varchar(64), created_at timestamptz NOT NULL,
          PRIMARY KEY(document_id,version,generation),
          FOREIGN KEY(document_id,version) REFERENCES ima.document_file_versions(document_id,version) ON DELETE RESTRICT
        );
        CREATE TABLE ima.document_chunks (
          document_id uuid NOT NULL, version integer NOT NULL, generation integer NOT NULL, ordinal integer NOT NULL CHECK(ordinal >= 0), text_content text NOT NULL, content_digest varchar(64) NOT NULL,
          embedding_status varchar(16) NOT NULL DEFAULT 'pending' CHECK(embedding_status IN ('pending','ready','failed')), model_id uuid, model_version integer, embedding_dimension integer CHECK(embedding_dimension > 0), embedding vector,
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          PRIMARY KEY(document_id,version,generation,ordinal),
          FOREIGN KEY(document_id,version,generation) REFERENCES ima.document_derived_text(document_id,version,generation) ON DELETE RESTRICT,
          CHECK(embedding IS NULL OR vector_dims(embedding)=embedding_dimension)
        );
        CREATE TABLE ima.ingestion_jobs (
          id uuid PRIMARY KEY, idempotency_key varchar(180) NOT NULL UNIQUE, document_id uuid NOT NULL, version integer NOT NULL, generation integer NOT NULL,
          stage varchar(16) NOT NULL CHECK(stage IN ('parse','chunk','embed','cleanup')), status varchar(24) NOT NULL CHECK(status IN ('blocked','queued','running','retryable','cancel_requested','cancelled','succeeded','failed','dead_letter')),
          completed_units integer NOT NULL DEFAULT 0 CHECK(completed_units >= 0), total_units integer NOT NULL DEFAULT 0 CHECK(total_units >= 0), attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0),
          lease_expires_at timestamptz, retry_at timestamptz, error_code varchar(64), correlation_id varchar(64), created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(document_id,version,generation,stage), FOREIGN KEY(document_id,version) REFERENCES ima.document_file_versions(document_id,version) ON DELETE RESTRICT
        );
        CREATE INDEX ix_ingestion_jobs_claim ON ima.ingestion_jobs(status,retry_at,lease_expires_at);
        CREATE TABLE ima.storage_cleanup_jobs (
          id uuid PRIMARY KEY, object_key varchar(1024) NOT NULL UNIQUE, document_id uuid, version integer, status varchar(24) NOT NULL CHECK(status IN ('queued','running','retryable','succeeded','dead_letter')), attempts integer NOT NULL DEFAULT 0 CHECK(attempts >= 0), next_eligible_at timestamptz NOT NULL, error_code varchar(64), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        );
        CREATE OR REPLACE FUNCTION ima.reject_file_version_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.object_state='verified' AND (OLD.object_key IS DISTINCT FROM NEW.object_key OR OLD.checksum IS DISTINCT FROM NEW.checksum OR OLD.size_bytes IS DISTINCT FROM NEW.size_bytes OR OLD.mime_type IS DISTINCT FROM NEW.mime_type OR OLD.original_filename IS DISTINCT FROM NEW.original_filename) THEN RAISE EXCEPTION 'verified file versions are immutable'; END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_document_file_version_immutable BEFORE UPDATE ON ima.document_file_versions FOR EACH ROW EXECUTE FUNCTION ima.reject_file_version_rewrite();
        """
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN IF EXISTS (SELECT 1 FROM ima.document_file_versions LIMIT 1) THEN RAISE EXCEPTION 'storage downgrade requires an explicit verified snapshot'; END IF; END $$;"""
    )
    op.execute("DROP TABLE IF EXISTS ima.storage_cleanup_jobs")
    op.execute("DROP TABLE IF EXISTS ima.ingestion_jobs")
    op.execute("DROP TABLE IF EXISTS ima.document_chunks")
    op.execute("DROP TABLE IF EXISTS ima.document_derived_text")
    op.execute(
        "DROP TRIGGER IF EXISTS trg_document_file_version_immutable ON ima.document_file_versions"
    )
    op.execute("DROP FUNCTION IF EXISTS ima.reject_file_version_rewrite()")
    op.execute("DROP TABLE IF EXISTS ima.document_file_versions")
