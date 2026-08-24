import { zValidator } from '@hono/zod-validator'
import { Hono } from 'hono'
import { z } from 'zod'
import { auth } from './auth/auth'
import { db } from './utils/db'
import { entity, item } from './schema'
import { actorFromSession, listVisibleEntityIds } from './utils/permissions'
import { and, desc, eq, inArray, sql } from 'drizzle-orm'
import { unionAll } from 'drizzle-orm/pg-core'
import type { SearchResult } from 'app/src-shared/utils/types'

const searchableType = z.enum(['folder', 'item'])

const app = new Hono().post('/',
  zValidator('json', z.object({
    workspaceId: z.string(),
    q: z.string().min(1),
    types: z.array(searchableType).default(searchableType.options),
    limit: z.int().min(1).max(100).default(40),
  })),
  async c => {
    const session = await auth.api.getSession({ headers: c.req.raw.headers })
    if (!session) return c.json({ error: 'Unauthorized' }, 401)

    const { workspaceId, q, types, limit } = c.req.valid('json')
    const actor = await actorFromSession(session.user.id, workspaceId)
    if (!actor) return c.json({ error: 'Workspace not found' }, 404)
    const visibleIds = await listVisibleEntityIds(actor)
    if (!visibleIds.length) return c.json([])

    const tsQuery = sql`websearch_to_tsquery('mixed', ${q})`
    const queries: any[] = []
    queries.push(
      db.select({
        id: entity.id,
        entityId: sql<string>`${entity.id}`.as('entityId'),
        type: entity.type,
        name: entity.name,
        content: sql<string | null>`null`.as('content'),
        textToHighlight: sql<string | null>`${entity.name}`.as('textToHighlight'),
        rank: sql<number>`ts_rank("entity"."search", ${tsQuery})`.as('rank'),
      })
        .from(entity)
        .where(and(
          eq(entity.rootId, workspaceId),
          inArray(entity.id, visibleIds),
          inArray(entity.type, types),
          sql`"entity"."search" @@ ${tsQuery}`,
        )),
    )

    if (types.includes('item')) {
      queries.push(
        db.select({
          id: item.id,
          entityId: sql<string>`${item.id}`.as('entityId'),
          type: entity.type,
          name: entity.name,
          content: sql<string | null>`${item.text}`.as('content'),
          textToHighlight: sql<string | null>`${item.text}`.as('textToHighlight'),
          rank: sql<number>`ts_rank("item"."search", ${tsQuery})`.as('rank'),
        })
          .from(item)
          .innerJoin(entity, and(eq(item.id, entity.id), eq(item.rootId, entity.rootId)))
          .where(and(
            eq(item.rootId, workspaceId),
            inArray(item.id, visibleIds),
            sql`"item"."search" @@ ${tsQuery}`,
          )),
      )
    }

    const union = queries.length === 1
      ? queries[0]
      // @ts-expect-error Drizzle expects discrete arguments
      : unionAll(queries[0], ...queries.slice(1))
    const headlineOptions = 'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, ShortWord=3, HighlightAll=FALSE, MaxFragments=2, FragmentDelimiter=" ... "'
    const rows = await db.select({
      id: sql<string>`"id"`,
      entityId: sql<string>`"entityId"`,
      type: sql<'folder' | 'item'>`"type"`,
      name: sql<string>`"name"`,
      content: sql<string | null>`"content"`,
      highlighted: sql<string | null>`ts_headline('mixed', "textToHighlight", ${tsQuery}, ${headlineOptions})`,
      rank: sql<number>`"rank"`,
    })
      .from(union.as('union_q'))
      .orderBy(desc(sql`rank`))
      .limit(limit)

    const results: SearchResult[] = rows.map(row => {
      const words = new Set<string>()
      row.highlighted?.matchAll(/<mark>(.*?)<\/mark>/gi).forEach(match => words.add(match[1]))
      return {
        id: row.id,
        entityId: row.entityId,
        type: row.type,
        name: row.name,
        content: row.content,
        words: [...words],
        rank: row.rank,
      }
    })
    return c.json(results)
  },
)

export default app
