"""Persist the grounded-Ask retrieval scope on conversations.

A conversation optionally pins retrieval to one folder subtree or one
document.  The scope is fixed at creation; follow-ups and retries inherit it.
The downgrade drops the constraint and column again.
"""

# Keep migration SQL as complete statements for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260912_0014"
down_revision = "20260910_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE ima.conversations
          ADD COLUMN IF NOT EXISTS scope jsonb;
        ALTER TABLE ima.conversations
          DROP CONSTRAINT IF EXISTS ck_conversations_scope;
        ALTER TABLE ima.conversations
          ADD CONSTRAINT ck_conversations_scope CHECK (
            scope IS NULL OR (
              jsonb_typeof(scope) = 'object'
              AND ((scope ? 'folderId')::int + (scope ? 'documentId')::int) = 1
              AND scope - 'folderId' - 'documentId' = '{}'::jsonb
              AND jsonb_typeof(COALESCE(scope->'folderId', scope->'documentId')) = 'string'
            )
          );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE ima.conversations DROP CONSTRAINT IF EXISTS ck_conversations_scope;
        ALTER TABLE ima.conversations DROP COLUMN IF EXISTS scope;
        """
    )
