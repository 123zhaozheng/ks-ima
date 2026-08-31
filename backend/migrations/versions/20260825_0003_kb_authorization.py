"""Knowledge base membership, share links, and folder hierarchy."""

# Keep migration SQL readable as complete statements.
# ruff: noqa: E501

from alembic import op

revision = "20260825_0003"
down_revision = "20260824_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ima.kb_members (
          kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
          role varchar(32) NOT NULL CHECK (role IN ('owner','editor','viewer')),
          state varchar(16) NOT NULL DEFAULT 'active' CHECK (state IN ('active')),
          version integer NOT NULL DEFAULT 1 CHECK (version > 0),
          joined_at timestamptz NOT NULL,
          PRIMARY KEY (kb_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_kb_members_user ON ima.kb_members(user_id,kb_id);
        CREATE INDEX IF NOT EXISTS ix_kb_members_kb_role ON ima.kb_members(kb_id,role);
        CREATE TABLE IF NOT EXISTS ima.kb_share_links (
          id varchar(32) PRIMARY KEY,
          kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          token_digest varchar(64) NOT NULL,
          token_salt varchar(64) NOT NULL,
          role varchar(32) NOT NULL CHECK (role IN ('editor','viewer')),
          created_by varchar(32) REFERENCES ima.users(id),
          expires_at timestamptz,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ux_kb_share_links_token_digest ON ima.kb_share_links(token_digest);
        CREATE INDEX IF NOT EXISTS ix_kb_share_links_kb ON ima.kb_share_links(kb_id,revoked_at,expires_at);
        CREATE TABLE IF NOT EXISTS ima.folders (
          id varchar(32) PRIMARY KEY, kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          parent_id varchar(32), name varchar(200) NOT NULL, normalized_name varchar(200) NOT NULL,
          order_key integer NOT NULL DEFAULT 0, lifecycle varchar(16) NOT NULL DEFAULT 'active' CHECK(lifecycle='active'),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0), is_root boolean NOT NULL DEFAULT false,
          created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          UNIQUE(kb_id,id),
          FOREIGN KEY(kb_id,parent_id) REFERENCES ima.folders(kb_id,id),
          CHECK ((is_root AND parent_id IS NULL AND id=kb_id) OR (NOT is_root AND parent_id IS NOT NULL AND id<>kb_id))
        );
        CREATE INDEX IF NOT EXISTS ix_folders_kb_parent ON ima.folders(kb_id,parent_id,lifecycle,order_key);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_folders_sibling_name ON ima.folders(kb_id,parent_id,normalized_name);
        CREATE TABLE IF NOT EXISTS ima.folder_closure (
          kb_id varchar(32) NOT NULL REFERENCES ima.knowledge_bases(id) ON DELETE CASCADE,
          ancestor_id varchar(32) NOT NULL, descendant_id varchar(32) NOT NULL, depth integer NOT NULL CHECK(depth>=0),
          PRIMARY KEY(kb_id,ancestor_id,descendant_id),
          FOREIGN KEY(kb_id,ancestor_id) REFERENCES ima.folders(kb_id,id) ON DELETE CASCADE,
          FOREIGN KEY(kb_id,descendant_id) REFERENCES ima.folders(kb_id,id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_folder_closure_descendant ON ima.folder_closure(kb_id,descendant_id,depth);
        CREATE INDEX IF NOT EXISTS ix_folder_closure_ancestor ON ima.folder_closure(kb_id,ancestor_id,depth);
        """
    )


def downgrade() -> None:
    # Target-only rows must not be silently destroyed by an operator downgrade.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM ima.kb_members LIMIT 1) THEN RAISE EXCEPTION 'knowledge base authorization downgrade requires an explicit snapshot'; END IF; END $$"
    )
    for table in (
        "folder_closure",
        "folders",
        "kb_share_links",
        "kb_members",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
