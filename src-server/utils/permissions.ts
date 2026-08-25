import { and, eq, inArray, isNull } from 'drizzle-orm'
import { db } from './db'
import { connector, entity } from '../schema'
import type { AclAction } from 'app/src-shared/utils/acl'
import { canAction } from 'app/src-shared/utils/acl'
import type { WorkspaceRole } from 'app/src-shared/utils/validators'
import { createHash, randomBytes } from 'node:crypto'
import { IMA_BRIDGE_TIMEOUT_MS, IMA_BRIDGE_TOKEN, privatePythonOrigin } from './config'

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
  if (bridgeConfigured()) {
    const target = await targetMember(userId, workspaceId)
    if (target?.source === 'target') return { userId, workspaceId, role: target.role }
    if (target?.source === 'denied') return undefined
  }
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
  if (bridgeConfigured()) {
    const target = await bridgeDecide(actor, entityId, action)
    if (target.source === 'target') return target.allowed
    if (target.source === 'denied') return false
  }
  const ancestors = await loadAncestors(entityId)
  return canAction(actor.role, actor.userId, ancestors, action)
}

export async function filterVisibleIds(actor: Actor, ids: string[]) {
  if (!ids.length) return []
  const bridge = await bridgeBatch(actor, ids, 'view')
  const visible: string[] = []
  for (const id of ids) {
    const target = bridge?.get(id)
    if (target?.source === 'target') {
      if (target.allowed) visible.push(id)
    } else if (target?.source === 'denied') {
      continue
    } else if (await can(actor, id, 'view')) {
      visible.push(id)
    }
  }
  return visible
}

export async function listVisibleEntityIds(actor: Actor, action: AclAction = 'view') {
  const rows = await db.select({ id: entity.id }).from(entity).where(eq(entity.rootId, actor.workspaceId))
  const bridge = await bridgeBatch(actor, rows.map(row => row.id), action)
  const visible: string[] = []
  for (const row of rows) {
    const target = bridge?.get(row.id)
    if (target?.source === 'target') {
      if (target.allowed) visible.push(row.id)
    } else if (target?.source !== 'denied' && await can(actor, row.id, action)) {
      visible.push(row.id)
    }
  }
  return visible
}

type BridgeAction = 'view_metadata' | 'view_content' | 'download' | 'ask' | 'create_child' | 'edit' | 'move' | 'delete' | 'manage_acl'
type BridgeDecision = { allowed: boolean, source: 'target' | 'legacy' | 'denied', reason: string, folderId?: string }

function bridgeConfigured() {
  return Boolean(privatePythonOrigin() && IMA_BRIDGE_TOKEN)
}

function bridgeAction(action: AclAction): BridgeAction {
  return ({ view: 'view_content', ask: 'ask', edit: 'edit', delete: 'delete', manage: 'manage_acl' } as Record<AclAction, BridgeAction>)[action]
}

async function bridgeRequest(path: string, body: unknown): Promise<Response | null> {
  if (!bridgeConfigured()) return null
  try {
    const origin = privatePythonOrigin()
    if (!origin) return null
    return await fetch(`${origin}/api/v1/internal/authorization/${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-ima-bridge-token': IMA_BRIDGE_TOKEN! },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(IMA_BRIDGE_TIMEOUT_MS),
    })
  } catch {
    return null
  }
}

async function bridgeDecide(actor: Actor, entityId: string, action: AclAction): Promise<BridgeDecision> {
  const response = await bridgeRequest('decide', { userId: actor.userId, workspaceId: actor.workspaceId, folderId: entityId, action: bridgeAction(action) })
  if (!response || !response.ok) return { allowed: false, source: 'denied', reason: 'bridge_unavailable' }
  const value = await response.json() as Partial<BridgeDecision>
  if (typeof value.allowed !== 'boolean' || !['target', 'legacy', 'denied'].includes(String(value.source))) {
    return { allowed: false, source: 'denied', reason: 'bridge_malformed' }
  }
  return { allowed: value.allowed, source: value.source as BridgeDecision['source'], reason: typeof value.reason === 'string' ? value.reason : 'unknown' }
}

async function bridgeBatch(actor: Actor, ids: string[], action: AclAction): Promise<Map<string, BridgeDecision> | null> {
  if (!bridgeConfigured()) return null
  const result = new Map<string, BridgeDecision>()
  for (let offset = 0; offset < ids.length; offset += 500) {
    const response = await bridgeRequest('batch', { userId: actor.userId, workspaceId: actor.workspaceId, folderIds: ids.slice(offset, offset + 500), action: bridgeAction(action) })
    if (!response || !response.ok) return new Map(ids.map(id => [id, { allowed: false, source: 'denied', reason: 'bridge_unavailable', folderId: id }]))
    const value = await response.json() as { items?: BridgeDecision[] }
    for (const item of value.items ?? []) {
      if (!item.folderId || typeof item.allowed !== 'boolean' || !['target', 'legacy', 'denied'].includes(item.source)) {
        return new Map(ids.map(id => [id, { allowed: false, source: 'denied', reason: 'bridge_malformed', folderId: id }]))
      }
      result.set(item.folderId, item)
    }
    for (const id of ids) {
      if (!result.has(id)) result.set(id, { allowed: false, source: 'denied', reason: 'bridge_incomplete', folderId: id })
    }
  }
  return result
}

async function targetMember(userId: string, workspaceId: string): Promise<{ role: WorkspaceRole, source: 'target' | 'legacy' | 'denied' } | null> {
  const response = await bridgeRequest('member', { userId, workspaceId })
  if (!response || !response.ok) return { role: 'guest', source: 'denied' }
  const value = await response.json() as { member?: { role: string } | null, source: 'target' | 'legacy' | 'denied' }
  if (!value.member) return null
  const roleMap: Record<string, WorkspaceRole> = { workspace_admin: 'admin', knowledge_manager: 'admin', editor: 'member', viewer: 'guest' }
  const role = roleMap[value.member.role]
  if (!role) return { role: 'guest', source: 'denied' }
  return { role, source: value.source }
}

export async function assertCan(actor: Actor, entityId: string, action: AclAction) {
  if (!(await can(actor, entityId, action))) {
    const err = new Error('Not found')
    ;(err as any).status = 404
    throw err
  }
}

export { and, eq, inArray, isNull }
