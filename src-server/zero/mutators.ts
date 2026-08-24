import { defineMutator, defineMutators } from '@rocicorp/zero'
import { mutators } from 'app/src-shared/mutators'
import { actorFromSession, assertCan } from '../utils/permissions'
import type { AclAction } from 'app/src-shared/utils/acl'
import { db } from '../utils/db'

async function requireEntityAction(userId: string | undefined, entityId: string, action: AclAction) {
  if (!userId || !entityId) throw new Error('Not found')
  const row = await db.query.entity.findFirst({
    where: { id: entityId },
    columns: { rootId: true },
  })
  if (!row) throw new Error('Not found')
  const actor = await actorFromSession(userId, row.rootId)
  if (!actor) throw new Error('Not found')
  await assertCan(actor, entityId, action)
  return actor
}

export const serverMutators = defineMutators(mutators, {
  createFolder: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { parentId: string }
    await requireEntityAction(ctx.userId, input.parentId, 'edit')
    await mutators.createFolder.fn({ tx, ctx, args: args as never })
  }),
  createItem: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { parentId: string }
    await requireEntityAction(ctx.userId, input.parentId, 'edit')
    await mutators.createItem.fn({ tx, ctx, args: args as never })
  }),
  createPage: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { parentId: string }
    await requireEntityAction(ctx.userId, input.parentId, 'edit')
    await mutators.createPage.fn({ tx, ctx, args: args as never })
  }),
  updateEntity: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { id: string }
    await requireEntityAction(ctx.userId, input.id, 'edit')
    await mutators.updateEntity.fn({ tx, ctx, args: args as never })
  }),
  updateEntityConf: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { id: string, updates?: Record<string, unknown>, deletes?: string[] }
    const changesAcl = Object.hasOwn(input.updates ?? {}, 'acl') || input.deletes?.includes('acl')
    await requireEntityAction(ctx.userId, input.id, changesAcl ? 'manage' : 'edit')
    await mutators.updateEntityConf.fn({ tx, ctx, args: args as never })
  }),
  moveEntities: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { ids: string[], to: string }
    await requireEntityAction(ctx.userId, input.to, 'edit')
    for (const id of input.ids) await requireEntityAction(ctx.userId, id, 'edit')
    await mutators.moveEntities.fn({ tx, ctx, args: args as never })
  }),
  recycleEntities: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { ids: string[] }
    for (const id of input.ids) await requireEntityAction(ctx.userId, id, 'delete')
    await mutators.recycleEntities.fn({ tx, ctx, args: args as never })
  }),
  restoreEntities: defineMutator(async ({ tx, ctx, args }) => {
    const input = args as { to: string }
    await requireEntityAction(ctx.userId, input.to, 'edit')
    await mutators.restoreEntities.fn({ tx, ctx, args: args as never })
  }),
})
