import { and, eq, sql } from 'drizzle-orm'
import { genId } from 'app/src-shared/utils/id'
import { db } from '../utils/db'
import { chunk, entity, item } from '../schema'
import { getObject } from '../utils/s3'
import { log } from '../utils/functions'
import { parseFileBytes } from './parse-file'
import { splitChunks } from './chunk-text'
import { safeEmbedTexts } from './embed'
import { workspaceKbSettings } from './settings'

type ParseStatus = 'queued' | 'parsing' | 'ready' | 'failed' | 'unparsed'

async function setParseConf(id: string, status: ParseStatus, extra: Record<string, unknown> = {}) {
  const row = await db.query.entity.findFirst({ where: { id } })
  if (!row) return
  await db.update(entity).set({
    conf: {
      ...row.conf,
      parseStatus: status,
      parseError: extra.parseError ?? null,
      indexed: extra.indexed ?? row.conf?.indexed,
    },
  }).where(eq(entity.id, id))
}

async function indexItem(id: string, rootId: string, text: string) {
  const settings = await workspaceKbSettings(rootId)
  const pieces = splitChunks(text, settings.chunkSize, settings.chunkOverlap)
  await db.delete(chunk).where(eq(chunk.entityId, id))
  const embeddings = await safeEmbedTexts(pieces, rootId)
  if (pieces.length) {
    await db.insert(chunk).values(pieces.map((text, ordinal) => ({
      id: genId(),
      rootId,
      entityId: id,
      ordinal,
      text,
      embedding: embeddings?.[ordinal] ?? null,
    })))
  }
  return Boolean(embeddings)
}

export async function parseItem(id: string) {
  const row = await db.query.item.findFirst({
    where: { id },
    with: { blob: true, entity: true },
  })
  if (!row?.blobId || !row.blob) return
  await setParseConf(id, 'parsing')
  try {
    const res = await getObject(row.blob.id)
    const buf = await res.arrayBuffer()
    const parsed = await parseFileBytes(buf, row.mimeType, row.entity?.name)
    if (!parsed?.text?.trim()) {
      await setParseConf(id, 'unparsed', { parseError: '未能提取文本' })
      return
    }
    await db.update(item).set({
      text: parsed.text,
      language: parsed.language,
    }).where(eq(item.id, id))

    const indexed = await indexItem(id, row.rootId, parsed.text)
    await setParseConf(id, 'ready', {
      indexed,
      parseError: indexed ? null : '未配置嵌入模型，仅关键词检索',
    })
  } catch (err) {
    log(`parseItem ${id} failed: ${String(err)}`)
    await setParseConf(id, 'failed', { parseError: String(err) })
  }
}

const inflight = new Set<string>()

export function enqueueParse(id: string) {
  if (inflight.has(id)) return
  inflight.add(id)
  setTimeout(() => {
    parseItem(id).catch(err => log(err)).finally(() => inflight.delete(id))
  }, 200)
}

/** Re-chunk + re-embed every parsed file in a workspace (Dify-style reindex). */
export async function reindexWorkspace(workspaceId: string): Promise<number> {
  const rows = await db.select({ id: item.id, text: item.text })
    .from(item)
    .where(and(
      eq(item.rootId, workspaceId),
      sql`${item.text} is not null and length(${item.text}) > 0`,
    ))
  let done = 0
  for (const row of rows) {
    try {
      await indexItem(row.id, workspaceId, row.text!)
      done += 1
    } catch (err) {
      log(`reindexWorkspace ${row.id} failed: ${String(err)}`)
    }
  }
  return done
}

export async function parseQueuedItems() {
  const rows = await db.select({ id: entity.id })
    .from(entity)
    .innerJoin(item, eq(item.id, entity.id))
    .where(and(
      eq(entity.type, 'item'),
      sql`${entity.conf}->>'parseStatus' = 'queued'`,
      sql`${item.blobId} is not null`,
    ))
    .limit(20)
  for (const row of rows) enqueueParse(row.id)

  const ready = await db.select({
    id: item.id,
    text: item.text,
    rootId: item.rootId,
  })
    .from(item)
    .where(sql`${item.text} is not null and length(${item.text}) > 0`)
    .limit(30)
  for (const row of ready) {
    if (!row.text) continue
    const existing = await db.select({ id: chunk.id }).from(chunk).where(eq(chunk.entityId, row.id)).limit(1)
    if (existing.length) continue
    try {
      await indexItem(row.id, row.rootId, row.text)
      await setParseConf(row.id, 'ready', { indexed: true, parseError: null })
    } catch (err) {
      log(`parseQueuedItems ${row.id}: ${String(err)}`)
    }
  }
}
