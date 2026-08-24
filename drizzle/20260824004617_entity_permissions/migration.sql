CREATE TABLE "entityPermission" (
	"workspaceId" varchar(16) NOT NULL,
	"entityId" varchar(16) NOT NULL,
	"userId" text NOT NULL,
	"canView" boolean NOT NULL,
	"canAsk" boolean NOT NULL,
	"canEdit" boolean NOT NULL,
	"canDelete" boolean NOT NULL,
	"canManage" boolean NOT NULL,
	CONSTRAINT "entityPermission_pkey" PRIMARY KEY("entityId", "userId")
);
--> statement-breakpoint
ALTER TABLE "entityPermission" ADD CONSTRAINT "entityPermission_workspaceId_workspace_id_fkey" FOREIGN KEY ("workspaceId") REFERENCES "workspace"("id") ON DELETE CASCADE;
--> statement-breakpoint
ALTER TABLE "entityPermission" ADD CONSTRAINT "entityPermission_entityId_entity_id_fkey" FOREIGN KEY ("entityId") REFERENCES "entity"("id") ON DELETE CASCADE;
--> statement-breakpoint
ALTER TABLE "entityPermission" ADD CONSTRAINT "entityPermission_userId_user_id_fkey" FOREIGN KEY ("userId") REFERENCES "user"("id") ON DELETE CASCADE;
--> statement-breakpoint
CREATE INDEX "entityPermission_workspaceId_userId_canView_index" ON "entityPermission" ("workspaceId", "userId", "canView");
--> statement-breakpoint
CREATE INDEX "entityPermission_userId_canView_index" ON "entityPermission" ("userId", "canView");
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_acl_granted(
	p_break_conf jsonb,
	p_role text,
	p_user_id text,
	p_action text
) RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
	SELECT CASE
		WHEN p_role = 'owner' THEN true
		WHEN p_break_conf IS NULL THEN CASE p_role
			WHEN 'guest' THEN p_action IN ('view', 'ask')
			WHEN 'member' THEN p_action IN ('view', 'ask', 'edit', 'delete')
			WHEN 'admin' THEN p_action IN ('view', 'ask', 'edit', 'delete', 'manage')
			ELSE false
		END
		ELSE EXISTS (
			SELECT 1
			FROM jsonb_array_elements(COALESCE(p_break_conf->'acl'->'aces', '[]'::jsonb)) AS ace
			WHERE (
				(ace->>'principalType' = 'role' AND ace->>'principalId' = p_role)
				OR (ace->>'principalType' = 'user' AND ace->>'principalId' = p_user_id)
			)
			AND COALESCE(ace->'actions', '[]'::jsonb) ? p_action
		)
	END
$$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_acl_can(
	p_break_conf jsonb,
	p_role text,
	p_user_id text,
	p_action text
) RETURNS boolean
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
	SELECT kb_acl_granted(p_break_conf, p_role, p_user_id, p_action)
		AND (p_action <> 'ask' OR kb_acl_granted(p_break_conf, p_role, p_user_id, 'view'))
$$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_nearest_acl_break(p_entity_id varchar(16))
RETURNS jsonb
LANGUAGE sql
STABLE
AS $$
	WITH RECURSIVE ancestors AS (
		SELECT e."id", e."rootId", e."parentId", e."conf", 0 AS depth
		FROM "entity" e
		WHERE e."id" = p_entity_id

		UNION ALL

		SELECT parent."id", parent."rootId", parent."parentId", parent."conf", child.depth + 1
		FROM "entity" parent
		JOIN ancestors child
			ON parent."id" = child."parentId"
			AND parent."rootId" = child."rootId"
	)
	SELECT "conf"
	FROM ancestors
	WHERE "conf"->'acl'->>'inherit' = 'false'
	ORDER BY depth
	LIMIT 1
$$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_rebuild_workspace_permissions(
	p_workspace_id varchar(16),
	p_user_id text DEFAULT NULL
) RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
	DELETE FROM "entityPermission"
	WHERE "workspaceId" = p_workspace_id
		AND (p_user_id IS NULL OR "userId" = p_user_id);

	INSERT INTO "entityPermission" (
		"workspaceId", "entityId", "userId",
		"canView", "canAsk", "canEdit", "canDelete", "canManage"
	)
	SELECT
		e."rootId",
		e."id",
		m."userId",
		kb_acl_can(b.break_conf, m."role", m."userId", 'view'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'ask'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'edit'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'delete'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'manage')
	FROM "entity" e
	JOIN "member" m ON m."workspaceId" = e."rootId"
	CROSS JOIN LATERAL (SELECT kb_nearest_acl_break(e."id") AS break_conf) b
	WHERE e."rootId" = p_workspace_id
		AND (p_user_id IS NULL OR m."userId" = p_user_id)
	ON CONFLICT ("entityId", "userId") DO UPDATE SET
		"workspaceId" = EXCLUDED."workspaceId",
		"canView" = EXCLUDED."canView",
		"canAsk" = EXCLUDED."canAsk",
		"canEdit" = EXCLUDED."canEdit",
		"canDelete" = EXCLUDED."canDelete",
		"canManage" = EXCLUDED."canManage";
END
$$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_rebuild_one_entity_permissions(p_entity_id varchar(16))
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
	v_workspace_id varchar(16);
BEGIN
	DELETE FROM "entityPermission" WHERE "entityId" = p_entity_id;
	SELECT e."rootId" INTO v_workspace_id
	FROM "entity" e
	JOIN "workspace" w ON w."id" = e."rootId"
	WHERE e."id" = p_entity_id;

	IF v_workspace_id IS NULL THEN
		RETURN;
	END IF;

	INSERT INTO "entityPermission" (
		"workspaceId", "entityId", "userId",
		"canView", "canAsk", "canEdit", "canDelete", "canManage"
	)
	SELECT
		e."rootId",
		e."id",
		m."userId",
		kb_acl_can(b.break_conf, m."role", m."userId", 'view'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'ask'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'edit'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'delete'),
		kb_acl_can(b.break_conf, m."role", m."userId", 'manage')
	FROM "entity" e
	JOIN "member" m ON m."workspaceId" = e."rootId"
	CROSS JOIN LATERAL (SELECT kb_nearest_acl_break(e."id") AS break_conf) b
	WHERE e."id" = p_entity_id;
END
$$;
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_entity_permission_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
	IF TG_OP = 'INSERT' THEN
		PERFORM kb_rebuild_one_entity_permissions(NEW."id");
		RETURN NEW;
	END IF;

	IF OLD."rootId" IS DISTINCT FROM NEW."rootId" THEN
		PERFORM kb_rebuild_workspace_permissions(OLD."rootId");
		PERFORM kb_rebuild_workspace_permissions(NEW."rootId");
	ELSIF OLD."parentId" IS DISTINCT FROM NEW."parentId"
		OR OLD."conf"->'acl' IS DISTINCT FROM NEW."conf"->'acl' THEN
		PERFORM kb_rebuild_workspace_permissions(NEW."rootId");
	END IF;
	RETURN NEW;
END
$$;
--> statement-breakpoint
CREATE TRIGGER kb_entity_permission_insert
AFTER INSERT ON "entity"
FOR EACH ROW EXECUTE FUNCTION kb_entity_permission_trigger();
--> statement-breakpoint
CREATE TRIGGER kb_entity_permission_update
AFTER UPDATE OF "rootId", "parentId", "conf" ON "entity"
FOR EACH ROW EXECUTE FUNCTION kb_entity_permission_trigger();
--> statement-breakpoint
CREATE OR REPLACE FUNCTION kb_member_permission_trigger()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
	IF TG_OP = 'DELETE' THEN
		DELETE FROM "entityPermission"
		WHERE "workspaceId" = OLD."workspaceId" AND "userId" = OLD."userId";
		RETURN OLD;
	END IF;

	IF TG_OP = 'UPDATE' AND (
		OLD."workspaceId" IS DISTINCT FROM NEW."workspaceId"
		OR OLD."userId" IS DISTINCT FROM NEW."userId"
	) THEN
		DELETE FROM "entityPermission"
		WHERE "workspaceId" = OLD."workspaceId" AND "userId" = OLD."userId";
	END IF;

	PERFORM kb_rebuild_workspace_permissions(NEW."workspaceId", NEW."userId");
	RETURN NEW;
END
$$;
--> statement-breakpoint
CREATE TRIGGER kb_member_permission_change
AFTER INSERT OR UPDATE OF "workspaceId", "userId", "role" OR DELETE ON "member"
FOR EACH ROW EXECUTE FUNCTION kb_member_permission_trigger();
--> statement-breakpoint
SELECT kb_rebuild_workspace_permissions(w."id") FROM "workspace" w;
--> statement-breakpoint
DO $$
DECLARE
	publication_name text;
BEGIN
	FOR publication_name IN
		SELECT pubname
		FROM pg_publication
		WHERE pubname LIKE '\_zero\_public\_%' ESCAPE '\'
	LOOP
		IF NOT EXISTS (
			SELECT 1
			FROM pg_publication_tables
			WHERE pubname = publication_name
				AND schemaname = 'public'
				AND tablename = 'entityPermission'
		) THEN
			EXECUTE format(
				'ALTER PUBLICATION %I ADD TABLE public.%I',
				publication_name,
				'entityPermission'
			);
		END IF;
	END LOOP;
END
$$;
