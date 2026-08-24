import 'dotenv/config'
import postgres from 'postgres'

const databaseUrl = process.env.DATABASE_URL
if (!databaseUrl) throw new Error('DATABASE_URL is required')

const sql = postgres(databaseUrl, { max: 1 })
const rollback = new Error('permission smoke rollback')
let evidence: Record<string, unknown> | undefined

function assert(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message)
}

try {
  const before = await sql<{ count: number }[]>`
    SELECT count(*)::int AS count FROM "entityPermission"
  `

  try {
    await sql.begin(async tx => {
      const [workspace] = await tx<{ id: string, ownerId: string }[]>`
        SELECT "id", "ownerId" FROM "workspace" ORDER BY "id" LIMIT 1
      `
      assert(workspace, 'Create a workspace before running the permission smoke test')

      const suffix = Date.now().toString(36)
      const userId = `perm-smoke-${suffix}`
      const memberId = `perm${suffix}`.slice(0, 16)
      await tx`
        INSERT INTO "user" ("id", "name", "email", "created_at", "updated_at")
        VALUES (${userId}, 'Permission smoke', ${`${userId}@invalid.local`}, now(), now())
      `
      await tx`
        INSERT INTO "member" ("id", "workspaceId", "userId", "role")
        VALUES (${memberId}, ${workspace.id}, ${userId}, 'guest')
      `

      const [inherited] = await tx<{ canView: boolean, canAsk: boolean }[]>`
        SELECT "canView", "canAsk"
        FROM "entityPermission"
        WHERE "entityId" = ${workspace.id} AND "userId" = ${userId}
      `
      assert(inherited?.canView && inherited.canAsk, 'Guest defaults were not materialized')

      await tx`
        UPDATE "entity"
        SET "conf" = jsonb_set(
          "conf",
          '{acl}',
          '{"inherit":false,"aces":[]}'::jsonb,
          true
        )
        WHERE "id" = ${workspace.id}
      `

      const [restricted] = await tx<{ canView: boolean, canAsk: boolean }[]>`
        SELECT "canView", "canAsk"
        FROM "entityPermission"
        WHERE "entityId" = ${workspace.id} AND "userId" = ${userId}
      `
      const [owner] = await tx<{ canView: boolean, canManage: boolean }[]>`
        SELECT "canView", "canManage"
        FROM "entityPermission"
        WHERE "entityId" = ${workspace.id} AND "userId" = ${workspace.ownerId}
      `
      assert(restricted && !restricted.canView && !restricted.canAsk, 'ACL break did not remove guest access')
      assert(owner?.canView && owner.canManage, 'Owner lockout protection failed')

      evidence = {
        inheritedGuest: inherited,
        restrictedGuest: restricted,
        owner,
      }
      throw rollback
    })
  } catch (error) {
    if (error !== rollback) throw error
  }

  const after = await sql<{ count: number }[]>`
    SELECT count(*)::int AS count FROM "entityPermission"
  `
  assert(before[0]?.count === after[0]?.count, 'Smoke-test transaction did not roll back')
  console.log(JSON.stringify({ ok: true, permissions: after[0]?.count, ...evidence }))
} finally {
  await sql.end()
}
