"""Persist structured parse IR and structure-aware chunk metadata."""

# Keep migration SQL as complete statements for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260914_0015"
down_revision = "20260912_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ima.document_derived_text
          ADD COLUMN IF NOT EXISTS ir jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE ima.document_chunks
          ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          ADD COLUMN IF NOT EXISTS heading_path text[],
          ADD COLUMN IF NOT EXISTS page_start integer,
          ADD COLUMN IF NOT EXISTS page_end integer,
          ADD COLUMN IF NOT EXISTS sheet_name text,
          ADD COLUMN IF NOT EXISTS chunk_type varchar(16) NOT NULL DEFAULT 'prose',
          ADD COLUMN IF NOT EXISTS token_count integer NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS chunker_version varchar(64) NOT NULL DEFAULT 'legacy';
        ALTER TABLE ima.document_chunks
          DROP CONSTRAINT IF EXISTS ck_document_chunks_metadata_object;
        ALTER TABLE ima.document_chunks
          ADD CONSTRAINT ck_document_chunks_metadata_object
            CHECK (jsonb_typeof(metadata) = 'object') NOT VALID,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_token_count,
          ADD CONSTRAINT ck_document_chunks_token_count CHECK (token_count >= 0) NOT VALID,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_page_range,
          ADD CONSTRAINT ck_document_chunks_page_range
            CHECK (page_start IS NULL OR page_end IS NULL OR page_end >= page_start) NOT VALID,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_type,
          ADD CONSTRAINT ck_document_chunks_type
            CHECK (chunk_type IN ('prose','table','code','heading')) NOT VALID;
        """
    )
    op.execute(
        """
        ALTER TABLE ima.document_chunks
          VALIDATE CONSTRAINT ck_document_chunks_metadata_object;
        ALTER TABLE ima.document_chunks
          VALIDATE CONSTRAINT ck_document_chunks_token_count;
        ALTER TABLE ima.document_chunks
          VALIDATE CONSTRAINT ck_document_chunks_page_range;
        ALTER TABLE ima.document_chunks
          VALIDATE CONSTRAINT ck_document_chunks_type;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ima.document_chunks
          DROP CONSTRAINT IF EXISTS ck_document_chunks_type,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_page_range,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_token_count,
          DROP CONSTRAINT IF EXISTS ck_document_chunks_metadata_object,
          DROP COLUMN IF EXISTS chunker_version,
          DROP COLUMN IF EXISTS token_count,
          DROP COLUMN IF EXISTS chunk_type,
          DROP COLUMN IF EXISTS sheet_name,
          DROP COLUMN IF EXISTS page_end,
          DROP COLUMN IF EXISTS page_start,
          DROP COLUMN IF EXISTS heading_path,
          DROP COLUMN IF EXISTS metadata;
        ALTER TABLE ima.document_derived_text DROP COLUMN IF EXISTS ir;
        """
    )
