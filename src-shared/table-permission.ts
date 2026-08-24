import type { DefaultSchema, Query } from '@rocicorp/zero'
import type { WorkspaceRole } from './utils/validators'
import { assert } from './utils/functions'
import type { Context } from './utils/types'

export const workspaceContentTables = [
  'message',
  'chat',
  'channel',
  'searchRecord',
  'search',
  'entity',
  'provider',
  'model',
  'page',
  'pagePatch',
  'assistant',
  'item',
  'shortcut',
  'translation',
  'translationRecord',
  'mcpPlugin',
  'toolCall',
] as const
export type WorkspaceContentTable = typeof workspaceContentTables[number]

export const workspaceTables = [
  ...workspaceContentTables,
  'workspace',
  'usage',
] as const
export type WorkspaceTable = typeof workspaceTables[number]

export function withRole<Q extends Query<WorkspaceTable, DefaultSchema, any>>(q: Q, userId: string, roles: WorkspaceRole[]) {
  return q.whereExists('member', q => q.where('userId', userId).where('role', 'IN', roles)) as Q
}
export function withMember<Q extends Query<WorkspaceTable, DefaultSchema, any>>(q: Q, userId: string) {
  return q.whereExists('member', q => q.where('userId', userId)) as Q
}
export function withReadable<Q extends Query<WorkspaceContentTable, DefaultSchema, any>>(q: Q, userId?: string) {
  if (!userId) return q.where('rootId', '') as Q
  return q.whereExists('permission', permission => permission
    .where('userId', userId)
    .where('canView', true)) as Q
}
export function withWritable<Q extends Query<WorkspaceContentTable, DefaultSchema, any>>(q: Q, userId: string) {
  return withRole(q, userId, ['owner', 'admin', 'member'])
}

export function assertAuthorized(userId: string | undefined): asserts userId {
  assert(userId, 'Unauthorized')
}

export function assertAdmin(ctx: Context) {
  assert(ctx.isAdmin, 'Forbidden')
}
