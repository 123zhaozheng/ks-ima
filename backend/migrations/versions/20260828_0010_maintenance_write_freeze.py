"""Add the maintenance write-freeze flag to system settings."""

from alembic import op

revision = "20260828_0010"
down_revision = "20260828_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """ALTER TABLE ima.system_settings
           ADD COLUMN IF NOT EXISTS maintenance_write_freeze boolean NOT NULL DEFAULT false"""
    )
    op.execute(
        """ALTER TABLE ima.system_settings
           ADD COLUMN IF NOT EXISTS maintenance_freeze_reason text"""
    )
    op.execute(
        """ALTER TABLE ima.system_settings
           ADD COLUMN IF NOT EXISTS maintenance_freeze_entered_at timestamptz"""
    )
    op.execute(
        """ALTER TABLE ima.system_settings
           ADD COLUMN IF NOT EXISTS maintenance_freeze_entered_by varchar(32)
           REFERENCES ima.users(id)"""
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE ima.system_settings DROP COLUMN IF EXISTS maintenance_freeze_entered_by"
    )
    op.execute(
        "ALTER TABLE ima.system_settings DROP COLUMN IF EXISTS maintenance_freeze_entered_at"
    )
    op.execute("ALTER TABLE ima.system_settings DROP COLUMN IF EXISTS maintenance_freeze_reason")
    op.execute("ALTER TABLE ima.system_settings DROP COLUMN IF EXISTS maintenance_write_freeze")
