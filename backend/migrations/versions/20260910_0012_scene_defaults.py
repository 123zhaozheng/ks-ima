"""Scene default models: one pointer row per workflow to a managed
capability profile.

The scene default is stored inside the model-governance domain: the pointer
references a ``capability_profiles`` row (system-managed alias ``场景默认``)
with ``ON DELETE RESTRICT``, so versioning, audit and FK integrity are all
inherited from the existing profile machinery. The workflow column repeats
the same CHECK enumeration as ``capability_profiles.workflow``.
"""

# Keep migration SQL as complete statements for operator review.
# ruff: noqa: E501

from alembic import op

revision = "20260910_0012"
down_revision = "20260829_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ima.scene_defaults (
          workflow varchar(32) PRIMARY KEY CHECK(workflow IN ('grounded_ask','title_generation','summarization','embedding','reranking')),
          profile_id uuid NOT NULL REFERENCES ima.capability_profiles(id) ON DELETE RESTRICT,
          updated_at timestamptz NOT NULL,
          updated_by varchar(32) REFERENCES ima.users(id)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ima.scene_defaults")
