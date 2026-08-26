"""Target search indexes, private conversations, and immutable citations."""

# SQL remains explicit for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260826_0007"
down_revision = "20260825_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_ts_config c
            JOIN pg_namespace n ON n.oid=c.cfgnamespace
            WHERE n.nspname='ima' AND c.cfgname='mixed'
          ) THEN
            CREATE TEXT SEARCH CONFIGURATION ima.mixed (PARSER=zhparser);
            ALTER TEXT SEARCH CONFIGURATION ima.mixed
              ADD MAPPING FOR n,v,a,b,z,s,t,i,j,l,x,g,m,q,d,f WITH simple;
            ALTER TEXT SEARCH CONFIGURATION ima.mixed
              ADD MAPPING FOR e WITH english_stem;
          END IF;
        END $$;
        ALTER TABLE ima.document_chunks
          ADD COLUMN IF NOT EXISTS workspace_id varchar(32);
        UPDATE ima.document_chunks c
          SET workspace_id=d.workspace_id
          FROM ima.documents d
          WHERE d.id=c.document_id AND c.workspace_id IS NULL;
        ALTER TABLE ima.document_chunks
          ALTER COLUMN workspace_id SET NOT NULL,
          ADD CONSTRAINT fk_document_chunks_workspace_document
            FOREIGN KEY(workspace_id,document_id) REFERENCES ima.documents(workspace_id,id) ON DELETE RESTRICT;
        ALTER TABLE ima.document_chunks
          ADD COLUMN IF NOT EXISTS search_vector tsvector
          GENERATED ALWAYS AS (to_tsvector('ima.mixed', left(text_content, 250000))) STORED;
        CREATE INDEX IF NOT EXISTS ix_document_chunks_search
          ON ima.document_chunks USING gin(search_vector);
        INSERT INTO ima.document_versions(document_id,version,kind,digest,created_by,created_at)
          SELECT fv.document_id,fv.version,'file',fv.checksum,fv.created_by,fv.created_at
          FROM ima.document_file_versions fv
          WHERE NOT EXISTS (
            SELECT 1 FROM ima.document_versions dv
            WHERE dv.document_id=fv.document_id AND dv.version=fv.version
          );
        ALTER TABLE ima.document_chunks
          ADD CONSTRAINT uq_document_chunks_identity_digest
          UNIQUE(document_id,version,generation,ordinal,content_digest);

        CREATE TABLE ima.chunk_search_indexes (
          id uuid PRIMARY KEY, workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE RESTRICT,
          model_id uuid NOT NULL REFERENCES ima.governed_models(id) ON DELETE RESTRICT,
          model_version integer NOT NULL CHECK(model_version > 0), embedding_dimension integer NOT NULL CHECK(embedding_dimension > 0),
          generation integer NOT NULL CHECK(generation > 0), index_name varchar(128) NOT NULL UNIQUE,
          status varchar(16) NOT NULL CHECK(status IN ('building','ready','active','retired','failed')),
          source_count integer NOT NULL DEFAULT 0 CHECK(source_count >= 0), source_digest varchar(64),
          activated_at timestamptz, retired_at timestamptz, created_at timestamptz NOT NULL,
          UNIQUE(workspace_id,model_id,model_version,embedding_dimension,generation)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_chunk_search_indexes_active
          ON ima.chunk_search_indexes(workspace_id,model_id,model_version,embedding_dimension)
          WHERE status='active';

        CREATE TABLE ima.conversations (
          id uuid PRIMARY KEY, workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE RESTRICT,
          owner_user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE RESTRICT,
          title varchar(200) NOT NULL, lifecycle varchar(16) NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','archived')),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(id,workspace_id,owner_user_id),
          FOREIGN KEY(workspace_id,owner_user_id) REFERENCES ima.workspace_members(workspace_id,user_id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_conversations_owner ON ima.conversations(workspace_id,owner_user_id,lifecycle,updated_at DESC,id);
        CREATE TABLE ima.conversation_messages (
          id uuid PRIMARY KEY, conversation_id uuid NOT NULL, workspace_id varchar(32) NOT NULL, owner_user_id varchar(32) NOT NULL,
          role varchar(16) NOT NULL CHECK(role IN ('user','assistant')),
          status varchar(24) NOT NULL CHECK(status IN ('pending','streaming','completed','knowledge_gap','failed','cancelled')),
          content text NOT NULL DEFAULT '' CHECK(octet_length(content) <= 100000), sequence integer NOT NULL CHECK(sequence > 0),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0), correlation_id varchar(64), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, completed_at timestamptz,
          UNIQUE(conversation_id,sequence),
          FOREIGN KEY(conversation_id,workspace_id,owner_user_id) REFERENCES ima.conversations(id,workspace_id,owner_user_id) ON DELETE RESTRICT
        );
        CREATE INDEX ix_conversation_messages_owner ON ima.conversation_messages(conversation_id,workspace_id,owner_user_id,sequence);
        CREATE TABLE ima.message_citations (
          message_id uuid NOT NULL REFERENCES ima.conversation_messages(id) ON DELETE RESTRICT,
          ordinal integer NOT NULL CHECK(ordinal > 0), document_id uuid NOT NULL, document_version integer NOT NULL CHECK(document_version > 0),
          file_generation integer, chunk_ordinal integer NOT NULL CHECK(chunk_ordinal >= 0), chunk_digest varchar(64) NOT NULL,
          quote text NOT NULL CHECK(octet_length(quote) <= 8000), rank integer NOT NULL CHECK(rank > 0), score double precision NOT NULL CHECK(score <> 'Infinity'::float8 AND score <> '-Infinity'::float8 AND score = score),
          created_at timestamptz NOT NULL, PRIMARY KEY(message_id,ordinal),
          FOREIGN KEY(document_id,document_version) REFERENCES ima.document_versions(document_id,version) ON DELETE RESTRICT,
          FOREIGN KEY(document_id,document_version,file_generation,chunk_ordinal,chunk_digest) REFERENCES ima.document_chunks(document_id,version,generation,ordinal,content_digest) ON DELETE RESTRICT
        );
        CREATE OR REPLACE FUNCTION ima.reject_completed_citation_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE message_status varchar(24);
        BEGIN
          SELECT status INTO message_status FROM ima.conversation_messages WHERE id=COALESCE(NEW.message_id,OLD.message_id);
          IF message_status='completed' THEN
            RAISE EXCEPTION 'completed message citations are immutable';
          END IF;
          RETURN NEW;
        END $$;
        CREATE TRIGGER trg_message_citation_immutable BEFORE UPDATE ON ima.message_citations
          FOR EACH ROW EXECUTE FUNCTION ima.reject_completed_citation_mutation();
        CREATE INDEX ix_message_citations_document ON ima.message_citations(document_id,document_version);
        """
    )


def downgrade() -> None:
    op.execute(
        """DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM ima.conversations LIMIT 1)
             OR EXISTS (SELECT 1 FROM ima.chunk_search_indexes LIMIT 1)
          THEN RAISE EXCEPTION 'search/conversation downgrade requires an explicit verified snapshot'; END IF;
        END $$;"""
    )
    op.execute("DROP TRIGGER IF EXISTS trg_message_citation_immutable ON ima.message_citations")
    op.execute("DROP FUNCTION IF EXISTS ima.reject_completed_citation_mutation()")
    op.execute("DROP TABLE IF EXISTS ima.message_citations")
    op.execute("DROP TABLE IF EXISTS ima.conversation_messages")
    op.execute("DROP TABLE IF EXISTS ima.conversations")
    op.execute("DROP TABLE IF EXISTS ima.chunk_search_indexes")
    op.execute("DROP INDEX IF EXISTS ima.ix_document_chunks_search")
    op.execute(
        "ALTER TABLE ima.document_chunks DROP CONSTRAINT IF EXISTS fk_document_chunks_workspace_document"
    )
    op.execute("ALTER TABLE ima.document_chunks DROP COLUMN IF EXISTS search_vector")
    op.execute("ALTER TABLE ima.document_chunks DROP COLUMN IF EXISTS workspace_id")
