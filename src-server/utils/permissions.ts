import { and, eq, inArray, isNull } from 'drizzle-orm'
import { db } from './db'
import { connector, entity } from '../schema'
import type { AclAction } from 'app/src-shared/utils/acl'
import { canAction } from 'app/src-shared/utils/acl'
import type { WorkspaceRole } from 'app/src-shared/utils/validators'
import { createHash, randomBytes } from 'node:crypto'

export type Actor = {
  userId: string
  role: WorkspaceRole
  workspaceId: string
  folderRootId?: string | null
  mode: 'read' | 'readwrite'
  connectorId?: string
}

export function hashApiKey(key: string) {
  return createHash('sha256').update(key).digest('hex')
}

export function generateApiKey() {
  const raw = `ima_${randomBytes(24).toString('base64url')}`
  return { raw, hash: hashApiKey(raw), prefix: raw.slice(0, 12) }
}

async function loadAncestors(entityId: string) {
  const confs: Array<Record<string, any>> = []
  let currentId: string | null = entityId
  const seen = new Set<string>()
  while (currentId && !seen.has(currentId)) {
    seen.add(currentId)
    const row = await db.query.entity.findFirst({
      where: { id: currentId },
      columns: { id: true, parentId: true, conf: true, rootId: true },
    })
    if (!row) break
    confs.push(row.conf ?? {})
    currentId = row.parentId
  }
  return confs
}

export async function getWorkspaceMember(userId: string, workspaceId: string) {
  return db.query.member.findFirst({
    where: { workspaceId, userId },
  })
}

export async function actorFromSession(userId: string, workspaceId: string): Promise<Actor | null> {
  const m = await getWorkspaceMember(userId, workspaceId)
  if (!m) return null
  return {
    userId,
    role: m.role,
    workspaceId,
    mode: m.role === 'guest' ? 'read' : 'readwrite',
  }
}

export async function actorFromApiKey(rawKey: string, workspaceId?: string): Promise<Actor | null> {
  const row = await db.query.connector.findFirst({
    where: {
      keyHash: hashApiKey(rawKey),
      revokedAt: { isNull: true },
    },
  })
  if (!row) return null
  if (row.expiresAt && row.expiresAt.getTime() < Date.now()) return null
  const wsId = workspaceId ?? row.workspaceId
  if (wsId !== row.workspaceId) return null
  const m = await getWorkspaceMember(row.createdBy, row.workspaceId)
  if (!m) return null
  await db.update(connector).set({ lastUsedAt: new Date() }).where(eq(connector.id, row.id))
  return {
    userId: row.createdBy,
    role: m.role,
    workspaceId: row.workspaceId,
    folderRootId: row.folderRootId,
    mode: row.mode,
    connectorId: row.id,
  }
}

export async function resolveActor(headers: Headers, workspaceId?: string): Promise<Actor | null> {
  const authz = headers.get('authorization')
  if (authz?.startsWith('Bearer ima_')) {
    return actorFromApiKey(authz.slice('Bearer '.length).trim(), workspaceId)
  }
  return null
}

export async function isUnderFolderRoot(entityId: string, folderRootId: string) {
  let currentId: string | null = entityId
  const seen = new Set<string>()
  while (currentId && !seen.has(currentId)) {
    if (currentId === folderRootId) return true
    seen.add(currentId)
    const row = await db.query.entity.findFirst({
      where: { id: currentId },
      columns: { parentId: true },
    })
    currentId = row?.parentId ?? null
  }
  return false
}

export async function can(actor: Actor, entityId: string, action: AclAction) {
  if (actor.mode === 'read' && (action === 'edit' || action === 'delete' || action === 'manage')) {
    return false
  }
  const row = await db.query.entity.findFirst({
    where: { id: entityId },
    columns: { id: true, rootId: true, parentId: true, conf: true },
  })
  if (!row || row.rootId !== actor.workspaceId) return false
  if (actor.folderRootId && !(await isUnderFolderRoot(entityId, actor.folderRootId))) return false
  const ancestors = await loadAncestors(entityId)
  return canAction(actor.role, actor.userId, ancestors, action)
}

export async function filterVisibleIds(actor: Actor, ids: string[]) {
  if (!ids.length) return []
  const visible: string[] = []
  for (const id of ids) {
    if (await can(actor, id, 'view')) visible.push(id)
  }
  return visible
}

export async function listVisibleEntityIds(actor: Actor, action: AclAction = 'view') {
  const rows = await db.select({ id: entity.id }).from(entity).where(eq(entity.rootId, actor.workspaceId))
  const visible: string[] = []
  for (const row of rows) {
    if (await can(actor, row.id, action)) visible.push(row.id)
  }
  return visible
}

export async function assertCan(actor: Actor, entityId: string, action: AclAction) {
  if (!(await can(actor, entityId, action))) {
    const err = new Error('Not found')
    ;(err as any).status = 404
    throw err
  }
}

export { and, eq, inArray, isNull }
