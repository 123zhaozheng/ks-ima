import { Hono } from 'hono'
import { zValidator } from '@hono/zod-validator'
import { z } from 'zod'
import { getSession } from './auth/session'
import { actorFromApiKey, actorFromSession, can, type Actor } from './utils/permissions'
import {
  kbAsk,
  kbCreateNote,
  kbDelete,
  kbGetFile,
  kbGetNote,
  kbGetTree,
  kbListDir,
  kbMkdir,
  kbMove,
  kbSearch,
  kbSetTags,
  kbUpdateNote,
  kbUploadFile,
} from './kb/ops'
import { enqueueParse, reindexWorkspace } from './kb/ingest'

export { kbAsk, kbListDir, kbSearch }

async function getActor(headers: Headers, workspaceId?: string): Promise<Actor | null> {
  const authz = headers.get('authorization')
  if (authz?.startsWith('Bearer ima_')) {
    return actorFromApiKey(authz.slice('Bearer '.length).trim(), workspaceId)
  }
  const session = await getSession(headers)
  if (!session || !workspaceId) return null
  return actorFromSession(session.user.id, workspaceId)
}

function notFound() {
  return { error: 'Not found' } as const
}

const app = new Hono()
  .post('/search', zValidator('json', z.object({
    workspaceId: z.string(),
    q: z.string().min(1),
    limit: z.int().min(1).max(50).optional(),
    folderId: z.string().optional(),
    tags: z.array(z.string()).optional(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    return c.json(await kbSearch(actor, body.q, {
      limit: body.limit,
      folderId: body.folderId,
      tags: body.tags,
    }))
  })
  .post('/ask', zValidator('json', z.object({
    workspaceId: z.string(),
    question: z.string().min(1),
    folderId: z.string().optional(),
    tags: z.array(z.string()).optional(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    return c.json(await kbAsk(actor, body.question, {
      folderId: body.folderId,
      tags: body.tags,
    }))
  })
  .post('/reparse', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    if (!(await can(actor, body.id, 'edit'))) return c.json(notFound(), 404)
    enqueueParse(body.id)
    return c.json({ ok: true })
  })
  .post('/reindex', zValidator('json', z.object({
    workspaceId: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor || (actor.role !== 'admin' && actor.role !== 'owner')) {
      return c.json({ error: 'Forbidden' }, 403)
    }
    const done = await reindexWorkspace(body.workspaceId)
    return c.json({ ok: true, reindexed: done })
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
  .post('/tree', zValidator('json', z.object({
    workspaceId: z.string(),
    folderId: z.string(),
    depth: z.int().min(0).max(4).default(2),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbGetTree(actor, body.folderId, body.depth)
    if ('error' in row && row.error) return c.json(row, 404)
    return c.json(row)
  })
  .post('/get-note', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbGetNote(actor, body.id)
    if ('error' in row && row.error) return c.json(row, 404)
    return c.json(row)
  })
  .post('/get-file', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbGetFile(actor, body.id)
    if ('error' in row && row.error) return c.json(row, 404)
    return c.json(row)
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
    const row = await kbCreateNote(actor, body.parentId, body.name, body.text)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
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
    const row = await kbUpdateNote(actor, body.id, body.text, body.mode)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
  })
  .post('/mkdir', zValidator('json', z.object({
    workspaceId: z.string(),
    parentId: z.string(),
    name: z.string().min(1),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbMkdir(actor, body.parentId, body.name)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
  })
  .post('/set-tags', zValidator('json', z.object({
    workspaceId: z.string(),
    id: z.string(),
    tags: z.array(z.string()),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbSetTags(actor, body.id, body.tags)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
  })
  .post('/move', zValidator('json', z.object({
    workspaceId: z.string(),
    ids: z.array(z.string()).min(1),
    to: z.string(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbMove(actor, body.ids, body.to)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
  })
  .post('/delete', zValidator('json', z.object({
    workspaceId: z.string(),
    ids: z.array(z.string()).min(1),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbDelete(actor, body.ids)
    if ('error' in row && row.error) return c.json(row, row.error === 'Forbidden' ? 403 : 404)
    return c.json(row)
  })
  .post('/upload', zValidator('json', z.object({
    workspaceId: z.string(),
    parentId: z.string(),
    name: z.string().min(1),
    mimeType: z.string().optional(),
    contentBase64: z.string().optional(),
    text: z.string().optional(),
  })), async c => {
    const body = c.req.valid('json')
    const actor = await getActor(c.req.raw.headers, body.workspaceId)
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    const row = await kbUploadFile(actor, body)
    if ('error' in row && row.error) {
      const status = row.error === 'Forbidden' ? 403 : row.error.startsWith('File too large') ? 413 : 400
      return c.json(row, status)
    }
    return c.json(row)
  })

export default app
