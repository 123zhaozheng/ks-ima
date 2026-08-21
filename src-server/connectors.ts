import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { auth } from './auth/auth'
import { db } from './utils/db'
import { connector } from './schema'
import { actorFromSession, generateApiKey } from './utils/permissions'
import { and, eq, isNull } from 'drizzle-orm'
import { genId } from 'app/src-shared/utils/id'

const app = new Hono()
  .get('/', async c => {
    const session = await auth.api.getSession({ headers: c.req.raw.headers })
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
    return c.json(rows.map(({ keyHash: _h, ...rest }) => rest))
  })
  .post('/', zValidator('json', z.object({
    workspaceId: z.string(),
    name: z.string().min(1),
    note: z.string().optional(),
    mode: z.enum(['read', 'readwrite']).default('read'),
    folderRootId: z.string().nullable().optional(),
    expiresAt: z.string().datetime().nullable().optional(),
  })), async c => {
    const session = await auth.api.getSession({ headers: c.req.raw.headers })
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
    const origin = new URL(c.req.url).origin
    return c.json({
      id,
      apiKey: raw,
      mcpUrl: `${origin}/api/mcp`,
      config: {
        mcpServers: {
          'intranet-ima': {
            url: `${origin}/api/mcp`,
            headers: { Authorization: `Bearer ${raw}` },
          },
        },
      },
    })
  })
  .delete('/:id', async c => {
    const session = await auth.api.getSession({ headers: c.req.raw.headers })
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

export default app
