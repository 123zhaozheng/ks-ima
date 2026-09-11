"""Scene-only model resolution: drop the knowledge-base profile assignments.

Model resolution now comes exclusively from ``ima.scene_defaults``; the
per-knowledge-base assignment table has no replacement routes and is removed.
The downgrade recreates the table (structure plus index) exactly as it was
defined by ``20260825_0004``; assignment data is intentionally not restored.
"""

# Keep migration SQL as complete statements for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260910_0013"
down_revision = "20260910_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ima.kb_profile_assignments")


def downgrade() -> None:
    op.execute(
        """
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
        """
    )
