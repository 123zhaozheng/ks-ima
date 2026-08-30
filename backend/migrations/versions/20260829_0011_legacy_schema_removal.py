"""Remove the retired legacy schema: drop the legacy public tables, ACL
functions, refcount trigger, and the legacy full-text-search configuration.

This is the point-of-no-return migration of the legacy deletion release. The
rollback window closed with the accepted cutover rehearsal and drill evidence
from the 08-24-legacy-migration-cutover task; the system is pre-production
with no live user data.

What is dropped:
- The 37 legacy ``public`` tables (drizzle-era Bun schema), CASCADE absorbing
  their indexes, constraints, triggers, generated tsvector columns, and
  owned sequences.
- The legacy ACL functions and the blob refcount trigger function from
  ``drizzle/20260824004617_entity_permissions`` and
  ``drizzle/20260317054607_create_trigger``.
- The legacy ``public.mixed`` text search configuration from
  ``drizzle/20260415115542_init_fts``. The ``ima.mixed`` configuration used
  by Python search lives in the ``ima`` schema and is untouched.

What is kept:
- Everything in the ``ima`` and ``ima_jobs`` schemas, including the
  checkpoint/history tables (``ima.legacy_knowledge_migration``,
  ``ima.legacy_model_governance_migration``, ``ima.legacy_identity_projection``)
  and all audit rows.
- The ``zhparser`` and ``vector`` extensions (used by ``ima``).

Downgrade policy: this migration is destructive and has no schema-level
downgrade. Post-deletion recovery is snapshot restore only — restore the
recorded pre-deletion database snapshot together with the matching
object-store inventory and deploy the pre-deletion image/configuration
(docs/legacy-cutover-runbook.md, "Post-Deletion Recovery").
"""

from alembic import op

revision = "20260829_0011"
down_revision = "20260828_0010"
branch_labels = None
depends_on = None

LEGACY_TABLES = (
    "account",
    "assistant",
    "blob",
    "channel",
    "chat",
    "connector",
    "entity",
    "entityAccess",
    "entityPermission",
    "globalSettings",
    "item",
    "mcpPlugin",
    "member",
    "mergePatchesRule",
    "message",
    "messageEntity",
    "model",
    "order",
    "page",
    "pagePatch",
    "plan",
    "planPrice",
    "provider",
    "search",
    "searchRecord",
    "session",
    "shortcut",
    "toolCall",
    "translation",
    "translationRecord",
    "two_factor",
    "usage",
    "user",
    "userData",
    "verification",
    "workspace",
    "workspaceInvitation",
)

LEGACY_FUNCTIONS = (
    "kb_acl_granted",
    "kb_acl_can",
    "kb_nearest_acl_break",
    "kb_rebuild_one_entity_permissions",
    "kb_rebuild_workspace_permissions",
    "kb_entity_permission_trigger",
    "kb_member_permission_trigger",
    "update_storage_and_refcount",
)


def upgrade() -> None:
    for table in LEGACY_TABLES:
        op.execute(f'DROP TABLE IF EXISTS public."{table}" CASCADE')
    # Drop the legacy functions by name regardless of signature; triggers on
    # the dropped tables are already gone via CASCADE.
    function_list = ", ".join(f"'{name}'" for name in LEGACY_FUNCTIONS)
    op.execute(
        f"""
        DO $legacy_cleanup$
        DECLARE
            proc_oid oid;
        BEGIN
            FOR proc_oid IN
                SELECT p.oid
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname IN ({function_list})
            LOOP
                EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', proc_oid::regprocedure);
            END LOOP;
        END $legacy_cleanup$;
        """
    )
    op.execute('DROP TEXT SEARCH CONFIGURATION IF EXISTS public."mixed" CASCADE')


def downgrade() -> None:
    raise RuntimeError(
        "20260829_0011_legacy_schema_removal is destructive and has no schema-level "
        "downgrade. Post-deletion recovery is snapshot restore only: restore the "
        "recorded pre-deletion database snapshot with the matching object-store "
        "inventory and deploy the pre-deletion image/configuration "
        "(docs/legacy-cutover-runbook.md, Post-Deletion Recovery)."
    )
