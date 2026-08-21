import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { auth } from './auth/auth'
import { db } from './utils/db'
import { entity, item, page } from './schema'
import { actorFromApiKey, actorFromSession, can, type Actor } from './utils/permissions'
import { and, desc, eq, sql } from 'drizzle-orm'
import { genId } from 'app/src-shared/utils/id'
import { mutators } from 'app/src-shared/mutators'
import { zdb } from './zero/db'

async function getActor(headers: Headers, workspaceId?: string): Promise<Actor | null> {
  const authz = headers.get('authorization')
  if (authz?.startsWith('Bearer ima_')) {
    return actorFromApiKey(authz.slice('Bearer '.length).trim(), workspaceId)
  }
  const session = await auth.api.getSession({ headers })
  if (!session || !workspaceId) return null
  return actorFromSession(session.user.id, workspaceId)
}

function notFound() {
  return { error: 'Not found' } as const
}

export async function kbSearch(actor: Actor, q: string, limit = 15) {
  const tsQuery = sql`websearch_to_tsquery('mixed', ${q})`
  const pageRows = await db.select({
    entityId: page.id,
    type: entity.type,
    name: entity.name,
    content: page.text,
    path: entity.name,
  })
    .from(page)
    .innerJoin(entity, and(eq(page.id, entity.id), eq(page.rootId, entity.rootId)))
    .where(and(eq(page.rootId, actor.workspaceId), sql`"page"."search" @@ ${tsQuery}`))
    .orderBy(desc(sql`ts_rank("page"."search", ${tsQuery})`))
    .limit(limit * 3)

  const itemRows = await db.select({
    entityId: item.id,
    type: entity.type,
    name: entity.name,
    content: item.text,
    path: entity.name,
  })
    .from(item)
    .innerJoin(entity, and(eq(item.id, entity.id), eq(item.rootId, entity.rootId)))
    .where(and(eq(item.rootId, actor.workspaceId), sql`"item"."search" @@ ${tsQuery}`))
    .orderBy(desc(sql`ts_rank("item"."search", ${tsQuery})`))
    .limit(limit * 3)

  const merged = [...pageRows, ...itemRows]
  const visible = []
  for (const row of merged) {
    if (await can(actor, row.entityId, 'view')) {
      visible.push({
        entityId: row.entityId,
        type: row.type === 'page' ? 'note' : row.type,
        title: row.name,
        quote: (row.content ?? '').slice(0, 800),
        path: row.path,
      })
    }
    if (visible.length >= limit) break
  }
  return visible
}

export async function kbAsk(actor: Actor, question: string) {
  const citations = await kbSearch(actor, question, 8)
  const knowledgeGap = citations.length === 0
  const answer = knowledgeGap
    ? '知识库未收录相关内容。请补充笔记或上传文件后再问。'
    : citations.map((c, i) => `[${i + 1}] ${c.title}: ${c.quote}`).join('\n\n')
  return { answer, citations, knowledgeGap }
}

export async function kbListDir(actor: Actor, folderId: string) {
  if (!(await can(actor, folderId, 'view'))) return null
  const children = await db.query.entity.findMany({
    where: { parentId: folderId, hidden: false },
    orderBy: { sortPriority: 'desc' },
  })
  const out = []
  for (const child of children) {
    if (await can(actor, child.id, 'view')) {
      out.push({
        id: child.id,
        type: child.type === 'page' ? 'note' : child.type,
        name: child.name,
        tags: child.conf?.tags ?? [],
      })
    }
  }
  return out
}

const app = new Hono()
  .post('/search', zValidator('json', z.object({
    workspaceId: z.string(),
    q: z.string().min(1),
    limit: z.int().min(1).max(50).default(15),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    return c.json(await kbSearch(actor, body.q, body.limit))
  })
  .post('/ask', zValidator('json', z.object({
    workspaceId: z.string(),
    question: z.string().min(1),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    return c.json(await kbAsk(actor, body.question))
  })
  .post('/list-dir', zValidator('json', z.object({
    workspaceId: z.string(),
    folderId: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const items = await kbListDir(actor, body.folderId)
    if (!items) return c.json(notFound(), 404)
    return c.json(items)
  })
  .post('/get-note', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.id, 'view'))) return c.json(notFound(), 404)
    const row = await db.query.page.findFirst({
      where: { id: body.id },
      with: { entity: true },
    })
    if (!row) return c.json(notFound(), 404)
    return c.json({
      id: row.id,
      title: row.entity?.name,
      text: row.text ?? '',
      tags: row.entity?.conf?.tags ?? [],
    })
  })
  .post('/create-note', zValidator('json', z.object({
    workspaceId: z.string(),
    parentId: z.string(),
    name: z.string().min(1),
    text: z.string().default(''),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.parentId, 'edit'))) return c.json(notFound(), 404)
    const id = genId()
    await zdb.transaction(async tx => {
      await mutators.createPage.fn({
        tx,
        ctx: { userId: actor.userId, locale: 'en-US' },
        args: { id, parentId: body.parentId, name: body.name },
      })
      if (body.text) {
        await tx.mutate.page.update({ id, text: body.text })
      }
    })
    return c.json({ id })
  })
  .post('/update-note', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
    text: z.string(),
    mode: z.enum(['replace', 'append']).default('replace'),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.id, 'edit'))) return c.json(notFound(), 404)
    const row = await db.query.page.findFirst({ where: { id: body.id } })
    if (!row) return c.json(notFound(), 404)
    const text = body.mode === 'append' ? `${row.text ?? ''}\n${body.text}` : body.text
    await zdb.transaction(async tx => {
      await tx.mutate.page.update({ id: body.id, text })
    })
    return c.json({ ok: true })
  })
  .post('/mkdir', zValidator('json', z.object({
    workspaceId: z.string(),
    parentId: z.string(),
    name: z.string().min(1),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.parentId, 'edit'))) return c.json(notFound(), 404)
    const id = genId()
    await zdb.transaction(async tx => {
      await mutators.createFolder.fn({
        tx,
        ctx: { userId: actor.userId, locale: 'en-US' },
        args: { id, parentId: body.parentId, name: body.name },
      })
    })
    return c.json({ id })
  })
  .post('/set-tags', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
    tags: z.array(z.string()),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.id, 'edit'))) return c.json(notFound(), 404)
    const row = await db.query.entity.findFirst({ where: { id: body.id } })
    if (!row) return c.json(notFound(), 404)
    await zdb.transaction(async tx => {
      await tx.mutate.entity.update({
        id: body.id,
        conf: { ...row.conf, tags: body.tags },
      })
    })
    return c.json({ ok: true })
  })

export default app
