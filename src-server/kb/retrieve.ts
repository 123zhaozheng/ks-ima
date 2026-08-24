import { and, desc, eq, inArray, sql } from 'drizzle-orm'
import { db } from '../utils/db'
import { chunk, entity } from '../schema'
import { can, isUnderFolderRoot, listVisibleEntityIds, type Actor } from '../utils/permissions'
import type { AclAction } from 'app/src-shared/utils/acl'
import { cosine, embedQuery } from './embed'
import { rerank } from './rerank'
import { workspaceKbSettings } from './settings'
import { weightedHybridScore, type KbSearchMode } from 'app/src-shared/kb-settings'

export interface Citation {
  entityId: string
  type: 'item'
  title: string | null
  path: string | null
  quote: string
  score: number
}

export type RetrieveOpts = {
  limit?: number
  folderId?: string
  tags?: string[]
}

type Hit = { id: string, entityId: string, text: string, name: string | null, rank: number }

function fuseHits(ftsRows: Hit[], vecRows: Hit[], mode: KbSearchMode, vectorWeight: number) {
  const byId = new Map<string, { entityId: string, text: string, name: string | null, fts?: number, vec?: number }>()
  for (const row of ftsRows) {
    byId.set(row.id, { entityId: row.entityId, text: row.text, name: row.name, fts: row.rank })
  }
  for (const row of vecRows) {
    const cur = byId.get(row.id)
    if (cur) cur.vec = row.rank
    else byId.set(row.id, { entityId: row.entityId, text: row.text, name: row.name, vec: row.rank })
  }
  const fused = new Map<string, { entityId: string, text: string, name: string | null, score: number }>()
  const scoreMode = mode === 'vector' && !vecRows.length ? 'keyword' : mode
  for (const [id, row] of byId) {
    const score = scoreMode === 'keyword'
      ? Math.max(0, Math.min(1, row.fts ?? 0))
      : scoreMode === 'vector'
        ? Math.max(0, Math.min(1, row.vec ?? 0))
        : weightedHybridScore(row.fts, row.vec, vectorWeight)
    fused.set(id, { entityId: row.entityId, text: row.text, name: row.name, score })
  }
  return fused
}

async function ftsHits(workspaceId: string, q: string, entityIds: string[]): Promise<Hit[]> {
  if (!entityIds.length) return []
  const tsQuery = sql`websearch_to_tsquery('mixed', ${q})`
  const rows = await db.select({
    id: chunk.id,
    entityId: chunk.entityId,
    text: chunk.text,
    name: entity.name,
    rank: sql<number>`ts_rank("chunk"."search", ${tsQuery})`.as('rank'),
  })
    .from(chunk)
    .innerJoin(entity, eq(chunk.entityId, entity.id))
    .where(and(
      eq(chunk.rootId, workspaceId),
      inArray(chunk.entityId, entityIds),
      sql`"chunk"."search" @@ ${tsQuery}`,
    ))
    .orderBy(desc(sql`ts_rank("chunk"."search", ${tsQuery})`))
    .limit(40)
  return rows
}

async function vectorHits(workspaceId: string, q: string, entityIds: string[]): Promise<Hit[]> {
  if (!entityIds.length) return []
  const vecQuery = await embedQuery(q, workspaceId).catch(() => null)
  if (!vecQuery) return []
  const pool = await db.select({
    id: chunk.id,
    entityId: chunk.entityId,
    text: chunk.text,
    name: entity.name,
    embedding: chunk.embedding,
  })
    .from(chunk)
    .innerJoin(entity, eq(chunk.entityId, entity.id))
    .where(and(
      eq(chunk.rootId, workspaceId),
      inArray(chunk.entityId, entityIds),
      sql`${chunk.embedding} is not null`,
    ))
    .limit(8000)
  return pool
    .map(row => ({
      id: row.id,
      entityId: row.entityId,
      text: row.text,
      name: row.name,
      rank: row.embedding ? cosine(vecQuery, row.embedding) : 0,
    }))
    .sort((a, b) => b.rank - a.rank)
    .slice(0, 40)
}

async function entityPath(entityId: string): Promise<string> {
  const names: string[] = []
  let currentId: string | null = entityId
  const seen = new Set<string>()
  while (currentId && !seen.has(currentId)) {
    seen.add(currentId)
    const row = await db.query.entity.findFirst({
      where: { id: currentId },
      columns: { name: true, parentId: true, rootId: true },
    })
    if (!row) break
    if (row.name) names.push(row.name)
    if (currentId === row.rootId) break
    currentId = row.parentId
  }
  return names.reverse().join('/')
}

async function entityTags(entityId: string): Promise<string[]> {
  const row = await db.query.entity.findFirst({
    where: { id: entityId },
    columns: { conf: true },
  })
  return (row?.conf?.tags ?? []) as string[]
}

async function scopedVisibleIds(actor: Actor, opts: RetrieveOpts, action: AclAction) {
  const visibleIds = await listVisibleEntityIds(actor, action)
  const scoped: string[] = []
  for (const id of visibleIds) {
    if (opts.folderId && !(await isUnderFolderRoot(id, opts.folderId))) continue
    if (opts.tags?.length) {
      const tags = await entityTags(id)
      if (!opts.tags.every(tag => tags.includes(tag))) continue
    }
    scoped.push(id)
  }
  return scoped
}

export async function kbRetrieve(
  actor: Actor,
  q: string,
  opts: RetrieveOpts = {},
  action: Extract<AclAction, 'view' | 'ask'> = 'view',
): Promise<Citation[]> {
  const settings = await workspaceKbSettings(actor.workspaceId)
  const limit = opts.limit ?? settings.topK
  const wantFts = settings.searchMode !== 'vector'
  const wantVec = settings.searchMode !== 'keyword'
  if (opts.folderId && !(await can(actor, opts.folderId, action))) return []
  const visibleIds = await scopedVisibleIds(actor, opts, action)

  let ftsRows: Hit[] = wantFts ? await ftsHits(actor.workspaceId, q, visibleIds) : []
  const vecRows: Hit[] = wantVec ? await vectorHits(actor.workspaceId, q, visibleIds) : []
  if (settings.searchMode === 'vector' && !vecRows.length) {
    ftsRows = await ftsHits(actor.workspaceId, q, visibleIds)
  }

  const fused = fuseHits(ftsRows, vecRows, settings.searchMode, settings.vectorWeight)

  // ACL / folder / tags before rerank so unauthorized text never leaves the retrieve layer.
  const allowed: Array<{ entityId: string, text: string, name: string | null, score: number }> = []
  const seenChunk = new Set<string>()
  for (const row of [...fused.values()].sort((a, b) => b.score - a.score)) {
    const key = row.entityId + row.text.slice(0, 40)
    if (seenChunk.has(key)) continue
    if (!(await can(actor, row.entityId, action))) continue
    seenChunk.add(key)
    allowed.push(row)
    if (allowed.length >= 20) break
  }

  let merged = allowed
  const rerankScores = await rerank(q, merged.map(r => r.text), actor.workspaceId)
  if (rerankScores) {
    merged = merged
      .map((row, i) => ({ ...row, score: rerankScores[i] ?? row.score }))
      .sort((a, b) => b.score - a.score)
  }

  const visible: Citation[] = []
  for (const row of merged) {
    if (!(await can(actor, row.entityId, 'view'))) continue
    if (settings.scoreThreshold > 0 && row.score < settings.scoreThreshold) continue
    visible.push({
      entityId: row.entityId,
      type: 'item',
      title: row.name,
      path: await entityPath(row.entityId),
      quote: row.text.slice(0, 800),
      score: row.score,
    })
    if (visible.length >= limit) break
  }
  return visible
}
