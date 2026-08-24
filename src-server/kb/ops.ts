import { createHash } from 'node:crypto'
import { eq } from 'drizzle-orm'
import { genId, randomId } from 'app/src-shared/utils/id'
import { mutators } from 'app/src-shared/mutators'
import { db } from '../utils/db'
import { blob, item } from '../schema'
import { can, type Actor } from '../utils/permissions'
import { putObject, presignedGetObject } from '../utils/s3'
import { enqueueParse } from './ingest'
import { kbRetrieve, type RetrieveOpts } from './retrieve'
import { zdb } from '../zero/db'
import { answerQuestion } from './answer'
import { chatGateway } from './models'

const MAX_UPLOAD_BYTES = 8 * 1024 * 1024

function ctxOf(actor: Actor) {
  return { userId: actor.userId, locale: 'en-US' as const }
}

function notFound() {
  return { error: 'Not found' as const }
}

function forbidden() {
  return { error: 'Forbidden' as const }
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

function publicType(type: string) {
  return type === 'page' ? 'note' : type
}

export async function kbSearch(actor: Actor, q: string, opts: RetrieveOpts = {}) {
  return kbRetrieve(actor, q, opts)
}

export async function kbAsk(actor: Actor, question: string, opts: RetrieveOpts = {}) {
  const citations = await kbRetrieve(actor, question, opts, 'ask')
  const gateway = citations.length ? await chatGateway(actor.workspaceId) : null
  const { answer, knowledgeGap } = await answerQuestion(question, citations, gateway)
  return { answer, citations, knowledgeGap }
}

export async function kbListDir(actor: Actor, folderId: string) {
  if (!(await can(actor, folderId, 'view'))) return null
  const children = await db.query.entity.findMany({
    where: { parentId: folderId, hidden: false },
    orderBy: { sortPriority: 'desc' },
  })
  const out: Array<{
    id: string
    type: string
    name: string | null
    tags: string[]
    parseStatus: string | null
  }> = []
  for (const child of children) {
    if (await can(actor, child.id, 'view')) {
      out.push({
        id: child.id,
        type: publicType(child.type),
        name: child.name,
        tags: (child.conf?.tags ?? []) as string[],
        parseStatus: typeof child.conf?.parseStatus === 'string' ? child.conf.parseStatus : null,
      })
    }
  }
  return out
}

export async function kbGetTree(actor: Actor, folderId: string, depth = 2) {
  const cap = Math.min(4, Math.max(0, depth))
  const budget = { n: 200 }

  async function nodeOf(id: string, remaining: number): Promise<Record<string, unknown> | null> {
    if (!(await can(actor, id, 'view'))) return null
    const row = await db.query.entity.findFirst({ where: { id } })
    if (!row) return null
    budget.n -= 1
    const children = remaining > 0 && budget.n > 0 ? await kbListDir(actor, id) : []
    const nested: Record<string, unknown>[] = []
    if (remaining > 0 && children) {
      for (const child of children) {
        if (budget.n <= 0) break
        if (child.type === 'folder') {
          const branch = await nodeOf(child.id, remaining - 1)
          if (branch) nested.push(branch)
        } else {
          budget.n -= 1
          nested.push(child)
        }
      }
    }
    return {
      id: row.id,
      type: publicType(row.type),
      name: row.name,
      tags: (row.conf?.tags ?? []) as string[],
      parseStatus: typeof row.conf?.parseStatus === 'string' ? row.conf.parseStatus : null,
      children: nested,
    }
  }

  const tree = await nodeOf(folderId, cap)
  return tree ?? notFound()
}

export async function kbGetNote(actor: Actor, id: string) {
  if (!(await can(actor, id, 'view'))) return notFound()
  const row = await db.query.page.findFirst({ where: { id }, with: { entity: true } })
  if (!row) return notFound()
  return {
    id: row.id,
    title: row.entity?.name,
    path: await entityPath(id),
    text: row.text ?? '',
    tags: row.entity?.conf?.tags ?? [],
  }
}

export async function kbGetFile(actor: Actor, id: string) {
  if (!(await can(actor, id, 'view'))) return notFound()
  const row = await db.query.item.findFirst({ where: { id }, with: { entity: true } })
  if (!row) return notFound()
  let downloadUrl: string | undefined
  if (row.blobId) {
    try {
      downloadUrl = await presignedGetObject(row.blobId, {
        expires: 1800,
        contentDisposition: `attachment; filename="${encodeURIComponent(row.entity?.name || 'file')}"`,
      })
    } catch {
      downloadUrl = undefined
    }
  }
  return {
    id: row.id,
    title: row.entity?.name,
    path: await entityPath(id),
    text: row.text ?? '',
    mimeType: row.mimeType,
    parseStatus: row.entity?.conf?.parseStatus ?? null,
    downloadUrl,
  }
}

export async function kbListTags(actor: Actor) {
  const rows = await db.query.entity.findMany({
    where: { rootId: actor.workspaceId },
    columns: { id: true, conf: true },
  })
  const tags = new Set<string>()
  for (const row of rows) {
    if (!(await can(actor, row.id, 'view'))) continue
    for (const tag of (row.conf?.tags ?? []) as string[]) tags.add(String(tag))
  }
  return [...tags]
}

export async function kbMkdir(actor: Actor, parentId: string, name: string) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, parentId, 'edit'))) return notFound()
  const id = genId()
  await zdb.transaction(async tx => {
    await mutators.createFolder.fn({
      tx,
      ctx: ctxOf(actor),
      args: { id, parentId, name },
    })
  })
  return { id }
}

export async function kbCreateNote(actor: Actor, parentId: string, name: string, text?: string) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, parentId, 'edit'))) return notFound()
  const id = genId()
  await zdb.transaction(async tx => {
    await mutators.createPage.fn({
      tx,
      ctx: ctxOf(actor),
      args: { id, parentId, name },
    })
    if (text) await tx.mutate.page.update({ id, text })
  })
  return { id }
}

export async function kbUpdateNote(actor: Actor, id: string, text: string, mode?: string) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, id, 'edit'))) return notFound()
  const row = await db.query.page.findFirst({ where: { id } })
  if (!row) return notFound()
  const next = mode === 'append' ? `${row.text ?? ''}\n${text}` : text
  await zdb.transaction(async tx => {
    await tx.mutate.page.update({ id, text: next })
  })
  return { ok: true }
}

export async function kbSetTags(actor: Actor, id: string, tags: string[]) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, id, 'edit'))) return notFound()
  const row = await db.query.entity.findFirst({ where: { id } })
  if (!row) return notFound()
  await zdb.transaction(async tx => {
    await tx.mutate.entity.update({ id, conf: { ...row.conf, tags } })
  })
  return { ok: true }
}

export async function kbMove(actor: Actor, ids: string[], to: string) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, to, 'edit'))) return notFound()
  for (const id of ids) {
    if (!(await can(actor, id, 'edit'))) return notFound()
  }
  await zdb.transaction(async tx => {
    await mutators.moveEntities.fn({
      tx,
      ctx: ctxOf(actor),
      args: { ids, to },
    })
  })
  return { ok: true }
}

export async function kbDelete(actor: Actor, ids: string[]) {
  if (actor.mode !== 'readwrite') return forbidden()
  for (const id of ids) {
    if (!(await can(actor, id, 'delete'))) return notFound()
  }
  await zdb.transaction(async tx => {
    await mutators.recycleEntities.fn({
      tx,
      ctx: ctxOf(actor),
      args: { workspaceId: actor.workspaceId, ids },
    })
  })
  return { ok: true }
}

function mimeFromName(name: string, fallback?: string) {
  const ext = name.split('.').pop()?.toLowerCase()
  const map: Record<string, string> = {
    pdf: 'application/pdf',
    doc: 'application/msword',
    docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ppt: 'application/vnd.ms-powerpoint',
    pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    xls: 'application/vnd.ms-excel',
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    txt: 'text/plain',
    md: 'text/markdown',
    html: 'text/html',
    csv: 'text/csv',
  }
  return fallback || (ext && map[ext]) || 'application/octet-stream'
}

export async function kbUploadFile(actor: Actor, args: {
  parentId: string
  name: string
  mimeType?: string
  contentBase64?: string
  text?: string
}) {
  if (actor.mode !== 'readwrite') return forbidden()
  if (!(await can(actor, args.parentId, 'edit'))) return notFound()
  const bytes = args.contentBase64
    ? Buffer.from(args.contentBase64, 'base64')
    : Buffer.from(args.text ?? '', 'utf8')
  if (!bytes.length) return { error: 'Empty file' as const }
  if (bytes.length > MAX_UPLOAD_BYTES) return { error: 'File too large (max 8MB via MCP)' as const }

  const id = genId()
  const mimeType = mimeFromName(args.name, args.mimeType)
  await zdb.transaction(async tx => {
    await mutators.createItem.fn({
      tx,
      ctx: ctxOf(actor),
      args: { id, parentId: args.parentId, name: args.name, mimeType },
    })
  })

  const sha256 = createHash('sha256').update(bytes).digest('base64')
  const existing = await db.query.blob.findFirst({
    where: { sha256, refCount: { gte: 1 } },
  })
  let blobId = existing?.id
  if (!blobId) {
    blobId = randomId()
    try {
      await putObject(blobId, bytes, { size: bytes.length })
    } catch (err) {
      return { error: String(err) }
    }
    await db.insert(blob).values({
      id: blobId,
      sha256,
      sha256Proof: sha256,
      size: bytes.length,
      refCount: 1,
    })
  }
  await db.update(item).set({ blobId }).where(eq(item.id, id))
  enqueueParse(id)
  return { id, parseStatus: 'queued' as const }
}
