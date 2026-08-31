"""Stable knowledge documents, immutable note versions, and migration checkpoints."""

# SQL statements remain readable as complete migration blocks.
# ruff: noqa: E501

from alembic import op

revision = "20260825_0005"
down_revision = "20260825_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ima.folders ADD COLUMN IF NOT EXISTS children_version bigint NOT NULL DEFAULT 0;

        CREATE TABLE IF NOT EXISTS ima.documents (
          id uuid PRIMARY KEY,
          kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          folder_id varchar(32) NOT NULL,
          kind varchar(16) NOT NULL CHECK(kind IN ('file','note')),
          title varchar(200) NOT NULL,
          normalized_title varchar(200) NOT NULL,
          order_key integer NOT NULL DEFAULT 0,
          lifecycle varchar(16) NOT NULL DEFAULT 'active' CHECK(lifecycle='active'),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0),
          current_version integer,
          file_state varchar(16) NOT NULL DEFAULT 'pending' CHECK(file_state IN ('pending','ready','failed')),
          mime_type varchar(255), size_bytes bigint CHECK(size_bytes IS NULL OR size_bytes >= 0),
          checksum varchar(128), storage_key varchar(1024),
          created_by varchar(32) REFERENCES ima.users(id), updated_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(kb_id,id),
          FOREIGN KEY(kb_id,folder_id) REFERENCES ima.folders(kb_id,id) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_documents_name
          ON ima.documents(kb_id,folder_id,kind,normalized_title);
        CREATE INDEX IF NOT EXISTS ix_documents_folder ON ima.documents(kb_id,folder_id,lifecycle,order_key,normalized_title,id);

        CREATE TABLE IF NOT EXISTS ima.document_versions (
          document_id uuid NOT NULL REFERENCES ima.documents(id) ON DELETE RESTRICT,
          version integer NOT NULL CHECK(version > 0),
          kind varchar(16) NOT NULL CHECK(kind IN ('file','note')),
          markdown text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          digest varchar(128) NOT NULL,
          created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL,
          PRIMARY KEY(document_id,version),
          CHECK(kind='note' OR markdown IS NULL)
        );
        CREATE OR REPLACE FUNCTION ima.reject_document_version_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.document_id IS DISTINCT FROM NEW.document_id OR OLD.version IS DISTINCT FROM NEW.version
             OR OLD.kind IS DISTINCT FROM NEW.kind OR OLD.markdown IS DISTINCT FROM NEW.markdown
             OR OLD.metadata IS DISTINCT FROM NEW.metadata OR OLD.digest IS DISTINCT FROM NEW.digest
             OR OLD.created_by IS DISTINCT FROM NEW.created_by OR OLD.created_at IS DISTINCT FROM NEW.created_at THEN
            RAISE EXCEPTION 'document versions are immutable';
          END IF;
          RETURN NEW;
        END $$;
        DROP TRIGGER IF EXISTS trg_document_version_immutable ON ima.document_versions;
        CREATE TRIGGER trg_document_version_immutable BEFORE UPDATE ON ima.document_versions
          FOR EACH ROW EXECUTE FUNCTION ima.reject_document_version_rewrite();

        CREATE TABLE IF NOT EXISTS ima.legacy_knowledge_migration (
          source_kind varchar(64) NOT NULL, source_id varchar(255) NOT NULL,
          source_fingerprint varchar(128) NOT NULL, target_kind varchar(32), target_id uuid,
          status varchar(16) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed','review')),
          attempts integer NOT NULL DEFAULT 0, last_error varchar(128), mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
          processed_at timestamptz, updated_at timestamptz NOT NULL,
          PRIMARY KEY(source_kind,source_id)
        );

        CREATE OR REPLACE FUNCTION ima.bump_folder_children_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='INSERT' THEN
            IF NEW.parent_id IS NOT NULL THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=NEW.parent_id; END IF;
          ELSIF TG_OP='DELETE' THEN
            IF OLD.parent_id IS NOT NULL THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=OLD.parent_id; END IF;
          ELSIF OLD.parent_id IS DISTINCT FROM NEW.parent_id OR OLD.name IS DISTINCT FROM NEW.name
             OR OLD.normalized_name IS DISTINCT FROM NEW.normalized_name OR OLD.order_key IS DISTINCT FROM NEW.order_key
             OR OLD.lifecycle IS DISTINCT FROM NEW.lifecycle THEN
            IF OLD.parent_id IS NOT NULL THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=OLD.parent_id; END IF;
            IF NEW.parent_id IS NOT NULL AND NEW.parent_id IS DISTINCT FROM OLD.parent_id THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=NEW.parent_id; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;
        DROP TRIGGER IF EXISTS trg_folder_children_version ON ima.folders;
        CREATE TRIGGER trg_folder_children_version AFTER INSERT OR UPDATE OR DELETE ON ima.folders
          FOR EACH ROW EXECUTE FUNCTION ima.bump_folder_children_version();

        CREATE OR REPLACE FUNCTION ima.bump_document_children_version() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP='INSERT' THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=NEW.folder_id;
          ELSIF TG_OP='DELETE' THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=OLD.folder_id;
          ELSIF OLD.folder_id IS DISTINCT FROM NEW.folder_id OR OLD.title IS DISTINCT FROM NEW.title
             OR OLD.normalized_title IS DISTINCT FROM NEW.normalized_title OR OLD.order_key IS DISTINCT FROM NEW.order_key
             OR OLD.lifecycle IS DISTINCT FROM NEW.lifecycle THEN
            UPDATE ima.folders SET children_version=children_version+1 WHERE id=OLD.folder_id;
            IF NEW.folder_id IS DISTINCT FROM OLD.folder_id THEN UPDATE ima.folders SET children_version=children_version+1 WHERE id=NEW.folder_id; END IF;
          END IF;
          IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END $$;
        DROP TRIGGER IF EXISTS trg_document_children_version ON ima.documents;
        CREATE TRIGGER trg_document_children_version AFTER INSERT OR UPDATE OR DELETE ON ima.documents
          FOR EACH ROW EXECUTE FUNCTION ima.bump_document_children_version();
        """
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM ima.documents LIMIT 1) OR EXISTS (SELECT 1 FROM ima.document_versions LIMIT 1)
        THEN RAISE EXCEPTION 'knowledge tree downgrade requires an explicit verified snapshot'; END IF;
        END $$;"""
    )
    op.execute("DROP TRIGGER IF EXISTS trg_document_children_version ON ima.documents")
    op.execute("DROP TRIGGER IF EXISTS trg_folder_children_version ON ima.folders")
    op.execute("DROP FUNCTION IF EXISTS ima.bump_document_children_version()")
    op.execute("DROP FUNCTION IF EXISTS ima.bump_folder_children_version()")
    op.execute("DROP FUNCTION IF EXISTS ima.reject_document_version_rewrite()")
    for table in (
        "legacy_knowledge_migration",
        "document_versions",
        "documents",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
    op.execute("ALTER TABLE ima.folders DROP COLUMN IF EXISTS children_version")
