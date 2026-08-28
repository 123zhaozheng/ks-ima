"""Add the source-expiry access path for durable MCP concurrency leases."""

from alembic import op

revision = "20260828_0009"
down_revision = "20260826_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """CREATE INDEX IF NOT EXISTS ix_mcp_concurrency_source_expiry
           ON ima.mcp_concurrency_leases(source_digest,expires_at)"""
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ima.ix_mcp_concurrency_source_expiry")
