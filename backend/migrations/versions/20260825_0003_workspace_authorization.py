"""Workspace membership, folder hierarchy, and normalized ACL state."""

# Keep migration SQL readable as complete statements.
# ruff: noqa: E501

from alembic import op

revision = "20260825_0003"
down_revision = "20260824_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep the authorization state additive. Legacy public tables remain read-only
    # migration inputs until the knowledge-tree cutover removes their consumers.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS ima.workspace_members (
          workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE CASCADE,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
          role varchar(32) NOT NULL CHECK (role IN ('workspace_admin','knowledge_manager','editor','viewer')),
          state varchar(16) NOT NULL DEFAULT 'active' CHECK (state IN ('active','invited','disabled')),
          granted_by varchar(32) REFERENCES ima.users(id), joined_at timestamptz,
          invited_at timestamptz, disabled_at timestamptz, updated_at timestamptz NOT NULL,
          version integer NOT NULL DEFAULT 1 CHECK (version > 0),
          PRIMARY KEY (workspace_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_workspace_members_user ON ima.workspace_members(user_id,state,workspace_id);
        CREATE INDEX IF NOT EXISTS ix_workspace_members_workspace_state ON ima.workspace_members(workspace_id,state,role);
        CREATE TABLE IF NOT EXISTS ima.workspace_invitations (
          id uuid PRIMARY KEY, workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE CASCADE,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
          role varchar(32) NOT NULL CHECK (role IN ('workspace_admin','knowledge_manager','editor','viewer')),
          token_digest varchar(128) NOT NULL UNIQUE, invited_by varchar(32) NOT NULL REFERENCES ima.users(id),
          expires_at timestamptz NOT NULL, accepted_at timestamptz, revoked_at timestamptz,
          created_at timestamptz NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_workspace_invitations_pending ON ima.workspace_invitations(workspace_id,user_id,expires_at);
        CREATE TABLE IF NOT EXISTS ima.workspace_groups (
          id uuid PRIMARY KEY, workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE CASCADE,
          name varchar(120) NOT NULL, normalized_name varchar(120) NOT NULL, created_by varchar(32) REFERENCES ima.users(id),
          created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, version integer NOT NULL DEFAULT 1 CHECK(version > 0),
          UNIQUE(workspace_id,normalized_name)
        );
        CREATE TABLE IF NOT EXISTS ima.workspace_group_members (
          group_id uuid NOT NULL REFERENCES ima.workspace_groups(id) ON DELETE CASCADE,
          user_id varchar(32) NOT NULL REFERENCES ima.users(id) ON DELETE CASCADE,
          granted_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL,
          PRIMARY KEY(group_id,user_id)
        );
        CREATE INDEX IF NOT EXISTS ix_workspace_group_members_user ON ima.workspace_group_members(user_id,group_id);
        CREATE TABLE IF NOT EXISTS ima.folders (
          id varchar(32) PRIMARY KEY, workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE CASCADE,
          parent_id varchar(32), name varchar(200) NOT NULL, normalized_name varchar(200) NOT NULL,
          order_key integer NOT NULL DEFAULT 0, lifecycle varchar(16) NOT NULL DEFAULT 'active' CHECK(lifecycle IN ('active','trashed')),
          version integer NOT NULL DEFAULT 1 CHECK(version > 0), is_root boolean NOT NULL DEFAULT false,
          acl_anchor_id varchar(32) NOT NULL, original_parent_id varchar(32), original_order_key integer,
          created_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
          trashed_at timestamptz,
          UNIQUE(workspace_id,id),
          FOREIGN KEY(workspace_id,parent_id) REFERENCES ima.folders(workspace_id,id),
          FOREIGN KEY(workspace_id,acl_anchor_id) REFERENCES ima.folders(workspace_id,id),
          CHECK ((is_root AND parent_id IS NULL AND id=workspace_id) OR (NOT is_root AND parent_id IS NOT NULL AND id<>workspace_id))
        );
        CREATE INDEX IF NOT EXISTS ix_folders_workspace_parent ON ima.folders(workspace_id,parent_id,lifecycle,order_key);
        CREATE INDEX IF NOT EXISTS ix_folders_workspace_anchor ON ima.folders(workspace_id,acl_anchor_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_folders_active_sibling_name ON ima.folders(workspace_id,parent_id,normalized_name) WHERE lifecycle='active';
        CREATE TABLE IF NOT EXISTS ima.folder_closure (
          workspace_id varchar(32) NOT NULL REFERENCES ima.workspaces(id) ON DELETE CASCADE,
          ancestor_id varchar(32) NOT NULL, descendant_id varchar(32) NOT NULL, depth integer NOT NULL CHECK(depth>=0),
          PRIMARY KEY(workspace_id,ancestor_id,descendant_id),
          FOREIGN KEY(workspace_id,ancestor_id) REFERENCES ima.folders(workspace_id,id) ON DELETE CASCADE,
          FOREIGN KEY(workspace_id,descendant_id) REFERENCES ima.folders(workspace_id,id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS ix_folder_closure_descendant ON ima.folder_closure(workspace_id,descendant_id,depth);
        CREATE INDEX IF NOT EXISTS ix_folder_closure_ancestor ON ima.folder_closure(workspace_id,ancestor_id,depth);
        CREATE TABLE IF NOT EXISTS ima.folder_acls (
          id uuid PRIMARY KEY, folder_id varchar(32) NOT NULL UNIQUE REFERENCES ima.folders(id) ON DELETE CASCADE,
          version integer NOT NULL DEFAULT 1 CHECK(version>0), created_by varchar(32) REFERENCES ima.users(id),
          updated_by varchar(32) REFERENCES ima.users(id), created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ima.folder_acl_entries (
          acl_id uuid NOT NULL REFERENCES ima.folder_acls(id) ON DELETE CASCADE,
          subject_type varchar(16) NOT NULL CHECK(subject_type IN ('role','group','user')),
          subject_id varchar(128) NOT NULL,
          action varchar(32) NOT NULL CHECK(action IN ('view_metadata','view_content','download','ask','create_child','edit','move','delete','manage_acl')),
          PRIMARY KEY(acl_id,subject_type,subject_id,action)
        );
        CREATE INDEX IF NOT EXISTS ix_folder_acl_entries_subject ON ima.folder_acl_entries(subject_type,subject_id,action,acl_id);
        CREATE TABLE IF NOT EXISTS ima.workspace_authorization_migration (
          source_kind varchar(32) NOT NULL, source_id varchar(128) NOT NULL,
          status varchar(16) NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','running','complete','failed')),
          attempts integer NOT NULL DEFAULT 0, source_fingerprint varchar(128), last_error varchar(128),
          processed_at timestamptz, updated_at timestamptz NOT NULL,
          PRIMARY KEY(source_kind,source_id)
        );
        """
    )


def downgrade() -> None:
    # Target-only rows must not be silently destroyed by an operator downgrade.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM ima.workspace_members LIMIT 1) THEN RAISE EXCEPTION 'workspace authorization downgrade requires an explicit snapshot'; END IF; END $$"
    )
    for table in (
        "folder_acl_entries",
        "folder_acls",
        "folder_closure",
        "folders",
        "workspace_group_members",
        "workspace_groups",
        "workspace_invitations",
        "workspace_members",
        "workspace_authorization_migration",
    ):
        op.execute(f"DROP TABLE IF EXISTS ima.{table} CASCADE")
