"""Create isolated foundation schemas and diagnostic state."""

from alembic import op

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS ima")
    op.execute("CREATE SCHEMA IF NOT EXISTS ima_jobs")
    # Both extensions are required by the approved target database image.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")
    op.execute(
        """CREATE TABLE IF NOT EXISTS ima_jobs.diagnostic_job (
            id uuid PRIMARY KEY,
            idempotency_key varchar(128) NOT NULL UNIQUE,
            status varchar(16) NOT NULL CHECK (
                status IN ('queued', 'running', 'succeeded', 'failed')
            ),
            attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            correlation_id varchar(64) NOT NULL,
            created_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        )"""
    )
    op.execute(
        """CREATE TABLE IF NOT EXISTS ima_jobs.worker_heartbeat (
            worker_name varchar(128) PRIMARY KEY,
            heartbeat_at timestamptz NOT NULL,
            queue_lag_seconds integer NOT NULL DEFAULT 0
        )"""
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_diagnostic_job_status "
        "ON ima_jobs.diagnostic_job (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ima_jobs.diagnostic_job")
    op.execute("DROP TABLE IF EXISTS ima_jobs.worker_heartbeat")
    op.execute("DROP SCHEMA IF EXISTS ima_jobs")
    op.execute("DROP SCHEMA IF EXISTS ima")
