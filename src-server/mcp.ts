import { Hono } from 'hono'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { z } from 'zod'
import { actorFromApiKey, can, type Actor } from './utils/permissions'
import { kbAsk, kbListDir, kbSearch } from './kb'
import { db } from './utils/db'
import { genId } from 'app/src-shared/utils/id'
import { mutators } from 'app/src-shared/mutators'
import { zdb } from './zero/db'

function toolText(data: unknown) {
  return { content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }] }
}

function createMcpServer(actor: Actor) {
  const server = new McpServer({ name: 'intranet-ima', version: '1.0.0' })

  server.tool('kb_list_workspaces', 'List workspaces this connector can access', {}, async () => {
    return toolText([{ id: actor.workspaceId }])
  })

  server.tool('kb_list_dir', 'List a folder', {
    folderId: z.string().describe('Folder entity id, defaults to workspace root').optional(),
  }, async ({ folderId }) => {
    const id = folderId || actor.folderRootId || actor.workspaceId
    const items = await kbListDir(actor, id)
    if (!items) return toolText({ error: 'Not found' })
    return toolText(items)
  })

  server.tool('kb_search', 'Keyword search notes and files in the knowledge base', {
    q: z.string(),
    limit: z.number().optional(),
  }, async ({ q, limit }) => toolText(await kbSearch(actor, q, limit ?? 15)))

  server.tool('kb_ask', 'Ask a question against the knowledge base. Returns answer plus citations.', {
    question: z.string(),
  }, async ({ question }) => toolText(await kbAsk(actor, question)))

  server.tool('kb_get_note', 'Get a markdown note', {
    id: z.string(),
  }, async ({ id }) => {
    if (!(await can(actor, id, 'view'))) return toolText({ error: 'Not found' })
    const row = await db.query.page.findFirst({ where: { id }, with: { entity: true } })
    if (!row) return toolText({ error: 'Not found' })
    return toolText({ id: row.id, title: row.entity?.name, text: row.text ?? '', tags: row.entity?.conf?.tags ?? [] })
  })

  server.tool('kb_get_file', 'Get parsed file text and metadata', {
    id: z.string(),
  }, async ({ id }) => {
    if (!(await can(actor, id, 'view'))) return toolText({ error: 'Not found' })
    const row = await db.query.item.findFirst({ where: { id }, with: { entity: true } })
    if (!row) return toolText({ error: 'Not found' })
    return toolText({ id: row.id, title: row.entity?.name, text: row.text ?? '', mimeType: row.mimeType })
  })

  server.tool('kb_list_tags', 'List tags used in the workspace', {}, async () => {
    const rows = await db.query.entity.findMany({
      where: { rootId: actor.workspaceId },
      columns: { conf: true },
    })
    const tags = new Set<string>()
    for (const row of rows) {
      for (const tag of row.conf?.tags ?? []) tags.add(String(tag))
    }
    return toolText([...tags])
  })

  if (actor.mode === 'readwrite') {
    server.tool('kb_mkdir', 'Create a folder', {
      parentId: z.string(),
      name: z.string(),
    }, async ({ parentId, name }) => {
      if (!(await can(actor, parentId, 'edit'))) return toolText({ error: 'Not found' })
      const id = genId()
      await zdb.transaction(async tx => {
        await mutators.createFolder.fn({
          tx,
          ctx: { userId: actor.userId, locale: 'en-US' },
          args: { id, parentId, name },
        })
      })
      return toolText({ id })
    })

    server.tool('kb_create_note', 'Create a markdown note in a folder', {
      parentId: z.string(),
      name: z.string(),
      text: z.string().optional(),
    }, async ({ parentId, name, text }) => {
      if (!(await can(actor, parentId, 'edit'))) return toolText({ error: 'Not found' })
      const id = genId()
      await zdb.transaction(async tx => {
        await mutators.createPage.fn({
          tx,
          ctx: { userId: actor.userId, locale: 'en-US' },
          args: { id, parentId, name },
        })
        if (text) await tx.mutate.page.update({ id, text })
      })
      return toolText({ id })
    })

    server.tool('kb_update_note', 'Replace or append note text', {
      id: z.string(),
      text: z.string(),
      mode: z.enum(['replace', 'append']).optional(),
    }, async ({ id, text, mode }) => {
      if (!(await can(actor, id, 'edit'))) return toolText({ error: 'Not found' })
      const row = await db.query.page.findFirst({ where: { id } })
      if (!row) return toolText({ error: 'Not found' })
      const next = mode === 'append' ? `${row.text ?? ''}\n${text}` : text
      await zdb.transaction(async tx => {
        await tx.mutate.page.update({ id, text: next })
      })
      return toolText({ ok: true })
    })

    server.tool('kb_set_tags', 'Set tags on a note or file', {
      id: z.string(),
      tags: z.array(z.string()),
    }, async ({ id, tags }) => {
      if (!(await can(actor, id, 'edit'))) return toolText({ error: 'Not found' })
      const row = await db.query.entity.findFirst({ where: { id } })
      if (!row) return toolText({ error: 'Not found' })
      await zdb.transaction(async tx => {
        await tx.mutate.entity.update({ id, conf: { ...row.conf, tags } })
      })
      return toolText({ ok: true })
    })
  }

  return server
}

const app = new Hono()
  .all('/', async c => {
    const authz = c.req.header('authorization')
    if (!authz?.startsWith('Bearer ima_')) {
      return c.json({ error: 'Unauthorized' }, 401)
    }
    const actor = await actorFromApiKey(authz.slice('Bearer '.length).trim())
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)

    const server = createMcpServer(actor)
    const { StreamableHTTPServerTransport } = await import('@modelcontextprotocol/sdk/server/streamableHttp.js')
    const transport = new StreamableHTTPServerTransport({ sessionIdGenerator: undefined })
    await server.connect(transport)
    const result = await transport.handleRequest(c.req.raw)
    if (result instanceof Response) return result
    return c.body(null, 202)
  })

export default app
