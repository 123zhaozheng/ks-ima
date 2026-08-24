import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { getSession } from './auth/session'
import { db } from './utils/db'
import { connector } from './schema'
import { actorFromSession, generateApiKey } from './utils/permissions'
import { and, eq, isNull } from 'drizzle-orm'
import { genId } from 'app/src-shared/utils/id'

function agentOriginFromRequest(reqUrl: string) {
  const url = new URL(reqUrl)
  if (url.port === '9015' || url.port === '9016') url.port = '3000'
  if (url.hostname === 'localhost') url.hostname = '127.0.0.1'
  return url.origin
}

const app = new Hono()
  .get('/workspaces', async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const rows = await db.query.member.findMany({
      where: { userId: session.user.id },
      with: { workspace: { columns: { id: true, name: true } } },
    })
    return c.json(rows.map(row => ({
      id: row.workspaceId,
      name: row.workspace?.name ?? null,
      role: row.role,
    })))
  })
  .get('/', async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const workspaceId = c.req.query('workspaceId')
    if (!workspaceId) return c.json({ error: 'workspaceId required' }, 400)
    const actor = await actorFromSession(session.user.id, workspaceId)
    if (!actor || (actor.role !== 'admin' && actor.role !== 'owner')) {
      return c.json({ error: 'Forbidden' }, 403)
    }
    const rows = await db.query.connector.findMany({
      where: { workspaceId, revokedAt: { isNull: true } },
    })
    return c.json(rows.map(row => Object.fromEntries(
      Object.entries(row).filter(([key]) => key !== 'keyHash'),
    )))
  })
  .post('/', zValidator('json', z.object({
    workspaceId: z.string(),
    name: z.string().min(1),
    note: z.string().optional(),
    mode: z.enum(['read', 'readwrite']).default('read'),
    folderRootId: z.string().nullable().optional(),
    expiresAt: z.string().datetime().nullable().optional(),
  })), async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const body = c.req.valid('json')
    const actor = await actorFromSession(session.user.id, body.workspaceId)
    if (!actor || (actor.role !== 'admin' && actor.role !== 'owner')) {
      return c.json({ error: 'Forbidden' }, 403)
    }
    const { raw, hash, prefix } = generateApiKey()
    const id = genId()
    await db.insert(connector).values({
      id,
      workspaceId: body.workspaceId,
      createdBy: session.user.id,
      name: body.name,
      note: body.note,
      keyHash: hash,
      keyPrefix: prefix,
      mode: body.mode,
      folderRootId: body.folderRootId ?? null,
      expiresAt: body.expiresAt ? new Date(body.expiresAt) : null,
      createdAt: new Date(),
    })
    const origin = agentOriginFromRequest(c.req.url)
    const mcpUrl = `${origin}/api/mcp`
    return c.json({
      id,
      apiKey: raw,
      mcpUrl,
      config: {
        mcpServers: {
          'intranet-ima': {
            url: mcpUrl,
            headers: { Authorization: `Bearer ${raw}` },
          },
        },
      },
    })
  })
  .delete('/:id', async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const id = c.req.param('id')
    const row = await db.query.connector.findFirst({ where: { id } })
    if (!row) return c.json({ error: 'Not found' }, 404)
    const actor = await actorFromSession(session.user.id, row.workspaceId)
    if (!actor || (actor.role !== 'admin' && actor.role !== 'owner')) {
      return c.json({ error: 'Forbidden' }, 403)
    }
    await db.update(connector).set({ revokedAt: new Date() }).where(and(eq(connector.id, id), isNull(connector.revokedAt)))
    return c.json({ ok: true })
  })
  .post('/:id/rotate', async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const id = c.req.param('id')
    const row = await db.query.connector.findFirst({ where: { id } })
    if (!row) return c.json({ error: 'Not found' }, 404)
    const actor = await actorFromSession(session.user.id, row.workspaceId)
    if (!actor || (actor.role !== 'admin' && actor.role !== 'owner')) {
      return c.json({ error: 'Forbidden' }, 403)
    }
    if (row.revokedAt) return c.json({ error: 'Already revoked' }, 400)
    const { raw, hash, prefix } = generateApiKey()
    await db.update(connector).set({ keyHash: hash, keyPrefix: prefix }).where(eq(connector.id, id))
    const origin = agentOriginFromRequest(c.req.url)
    const mcpUrl = `${origin}/api/mcp`
    return c.json({
      id,
      apiKey: raw,
      mcpUrl,
      config: {
        mcpServers: {
          'intranet-ima': {
            url: mcpUrl,
            headers: { Authorization: `Bearer ${raw}` },
          },
        },
      },
    })
  })

export default app
