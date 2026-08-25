import { z } from 'zod'
import type { DefaultSchema, Query, QueryResultType, Row } from '@rocicorp/zero'
import { defineQueries, defineQuery } from '@rocicorp/zero'
import { zql } from './schema.gen'
import { assertAuthorized, withMember, withReadable, withRole } from './table-permission'
import type { EntityListOptions } from './utils/validators'
import { entityListOptionsSchema, entityStartSchema, entityTypeSchema } from './utils/validators'

type EntityQuery = Query<'entity', DefaultSchema, any>
function withParent(q: EntityQuery, depth: number, userId?: string) {
  if (depth) q = q.related('parent', q => withParent(withReadable(q, userId), depth - 1, userId))
  return q
}
function withChildren(
  q: EntityQuery,
  depth: number,
  userId?: string,
  refine: (q: EntityQuery) => EntityQuery = q => q,
) {
  if (depth) {
    q = q.related('children', q => withChildren(
      withReadable(refine(q), userId).related('item'),
      depth - 1,
      userId,
      refine,
    ))
  }
  return q
}
function fullMessage(q: Query<'message', DefaultSchema>, userId?: string) {
  return q
    .related('toolCalls')
    .related('assistant', q => q.related('entity'))
    .related('user')
    .related('entities', q => withReadable(q.related('item'), userId))
}
function filterEntities(q: EntityQuery, { type, hidden, orderBy }: EntityListOptions) {
  if (type) q = q.where('type', type)
  if (hidden != null) q = q.where('hidden', hidden)
  return q
    .orderBy('sortPriority', 'desc')
    .orderBy(...orderBy)
}

export const queries = defineQueries({
  searchWithRecords: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.search
          .where('id', id)
          .related('records'),
        ctx.userId,
      ).one()
    },
  ),
  recentSearches: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(
        zql.search
          .where('rootId', workspaceId)
          .related('records')
          .orderBy('id', 'desc')
          .limit(20),
        ctx.userId,
      )
    },
  ),
  searchRecord: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.searchRecord.where('id', id),
        ctx.userId,
      ).one()
    },
  ),
  fullChat: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.chat.where('id', id).related('messages', q => fullMessage(q, ctx.userId)),
        ctx.userId,
      ).one()
    },
  ),
  recentChats: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(
        zql.chat
          .where('rootId', workspaceId)
          .related('messages', q => fullMessage(q, ctx.userId))
          .orderBy('id', 'desc').limit(20),
        ctx.userId,
      )
    },
  ),
  entity: defineQuery(
    z.object({
      id: z.string(),
      parent: z.object({
        depth: z.int(),
      }).nullish(),
      children: z.object({
        depth: z.int(),
        limit: z.int().default(40),
        start: entityStartSchema.nullish(),
        ...entityListOptionsSchema.shape,
      }).nullish(),
    }),
    ({ ctx, args: { id, parent, children } }) => {
      let q = zql.entity.where('id', id)
      if (parent) q = withParent(q, parent.depth, ctx.userId)
      if (children) {
        q = withChildren(q, children.depth, ctx.userId, q => {
          q = filterEntities(q, children)
          if (children.start) q = q.start(children.start)
          return q.limit(children.limit)
        })
      }
      return withReadable(q as Query<'entity', DefaultSchema, FullEntity>, ctx.userId).one()
    },
  ),
  workspaceFolders: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(
        zql.entity
          .where('rootId', workspaceId)
          .where('type', 'folder')
          .orderBy('name', 'asc'),
        ctx.userId,
      )
    },
  ),
  shortcuts: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(zql.shortcut.where('rootId', workspaceId), ctx.userId)
    },
  ),
  fullAssistant: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.assistant
          .where('id', id)
          .related('entity'),
        ctx.userId,
      ).one()
    },
  ),
  assistants: defineQuery(
    z.object({
      workspaceId: z.string(),
      limit: z.number().nullish(),
    }),
    ({ ctx, args: { workspaceId, limit } }) => {
      let q = zql.assistant
        .where('rootId', workspaceId)
        .related('entity')
        .orderBy('id', 'desc')
      if (limit) q = q.limit(limit)
      return withReadable(
        q,
        ctx.userId,
      )
    },
  ),
  fullPage: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.page
          .where('id', id)
          .related('entity')
          .related('patches', q => q.related('user')),
        ctx.userId,
      ).one()
    },
  ),
  recentPages: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(
        zql.page
          .where('rootId', workspaceId)
          .related('entity')
          .related('patches')
          .orderBy('id', 'desc')
          .limit(20),
        ctx.userId,
      )
    },
  ),
  recentItems: defineQuery(
    z.string(),
    ({ ctx, args: workspaceId }) => {
      return withReadable(
        zql.item
          .where('rootId', workspaceId)
          .related('blob')
          .orderBy('id', 'desc')
          .limit(20),
        ctx.userId,
      )
    },
  ),
  fullItem: defineQuery(
    z.string(),
    ({ ctx, args: id }) => {
      return withReadable(
        zql.item.where('id', id).related('blob'),
        ctx.userId,
      ).one()
    },
  ),
  searchEntities: defineQuery(
    z.object({
      workspaceId: z.string(),
      query: z.string(),
      type: entityTypeSchema.nullish(),
      limit: z.number().default(20),
    }),
    ({ ctx, args: { workspaceId, query, type, limit } }) => {
      let q = zql.entity
        .where('name', 'ILIKE', `%${query}%`)
        .where('rootId', workspaceId)
        .orderBy('id', 'desc')
        .limit(limit)
      if (type) q = q.where('type', type)
      return withReadable(q, ctx.userId)
    },
  ),
  fullWorkspace: defineQuery(
    z.string(),
    ({ ctx: { userId }, args: workspaceId }) => {
      assertAuthorized(userId)
      return withMember(zql.workspace, userId)
        .where('id', workspaceId)
        .related('member', q => q.where('userId', userId).related('user'))
        .related('members', q => q.related('user'))
        .related('invitations', q => q.where('inviterId', userId).orderBy('expiresAt', 'desc'))
        .one()
    },
  ),
  userData: defineQuery(
    z.undefined(),
    ({ ctx }) => {
      assertAuthorized(ctx.userId)
      return zql.userData.where('id', ctx.userId).one()
    },
  ),
  currentUser: defineQuery(
    z.undefined(),
    ({ ctx }) => {
      assertAuthorized(ctx.userId)
      return zql.user.where('id', ctx.userId).one()
    },
  ),
  fullInvitation: defineQuery(
    z.string(),
    ({ args: token }) => {
      return zql.workspaceInvitation
        .where('token', token)
        .related('workspace')
        .related('inviter')
        .one()
    },
  ),
  workspaces: defineQuery(
    z.undefined(),
    ({ ctx: { userId } }) => {
      assertAuthorized(userId)
      return withMember(zql.workspace, userId)
    },
  ),
  listTrash: defineQuery(
    z.object({
      workspaceId: z.string(),
      start: entityStartSchema.nullish(),
      limit: z.number().default(40),
      ...entityListOptionsSchema.shape,
    }),
    ({ ctx: { userId }, args: { workspaceId, start, limit, ...listOptions } }) => {
      assertAuthorized(userId)
      let q = zql.entity.whereExists('trashWorkspace', q =>
        withRole(q.where('id', workspaceId), userId, ['owner', 'admin']),
      )
      q = filterEntities(q, listOptions)
      if (start) q = q.start(start)
      return q.limit(limit)
    },
  ),
  entityAccesses: defineQuery(
    z.string(),
    ({ ctx: { userId }, args: workspaceId }) => {
      assertAuthorized(userId)
      return zql.entityAccess
        .where('userId', userId)
        .where('rootId', workspaceId)
        .whereExists('permission', permission => permission
          .where('userId', userId)
          .where('canView', true))
        .related('entity', entity => withReadable(entity, userId))
        .orderBy('time', 'desc')
    },
  ),
  globalSettings: defineQuery(z.undefined(), () => {
    return zql.globalSettings.one()
  }),
})

export type SearchWithRecords = NonNullable<QueryResultType<typeof queries.searchWithRecords>>
export type FullChat = NonNullable<QueryResultType<typeof queries.fullChat>>
export type FullMessage = ReturnType<typeof fullMessage> extends Query<'message', DefaultSchema, infer T> ? T : never
export type ToolCall = FullMessage['toolCalls'][number]
export type FullAssistant = NonNullable<QueryResultType<typeof queries.fullAssistant>>
export type FullPage = NonNullable<QueryResultType<typeof queries.fullPage>>
export type FullItem = NonNullable<QueryResultType<typeof queries.fullItem>>

export type FullEntity = Row['entity'] & { parent?: FullEntity, children?: FullEntity[], item?: Row['item'] | null }
export type EntityWithItem = Row['entity'] & { item?: Row['item'] | null }

export type FullWorkspace = NonNullable<QueryResultType<typeof queries.fullWorkspace>>
export type FullMember = FullWorkspace['members'][number]
