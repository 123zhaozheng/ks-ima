import { Hono } from 'hono'
import { getSession } from './auth/session'
import { db } from './utils/db'
import { model, workspace, globalSettings } from './schema'
import { and, eq } from 'drizzle-orm'
import { zValidator } from '@hono/zod-validator'
import { createInsertSchema, createUpdateSchema } from 'drizzle-zod'
import { avatarSchema, modelInputTypesSchema } from 'app/src-shared/utils/validators'
import { z } from 'zod'
import { genId } from 'app/src-shared/utils/id'
import { PUBLIC_ROOT_ID } from 'app/src-shared/utils/config'

const adminModelSchema = createInsertSchema(model).omit({
  id: true,
  rootId: true,
  entityId: true,
}).extend({
  avatar: avatarSchema.nullish(),
  inputTypes: modelInputTypesSchema.nullish(),
})
export type AdminModel = z.infer<typeof adminModelSchema>

const app = new Hono()
  .post('/addModel',
    zValidator('json', adminModelSchema),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const props = c.req.valid('json')
      await db.insert(model).values({
        id: genId(),
        rootId: PUBLIC_ROOT_ID,
        entityId: PUBLIC_ROOT_ID,
        ...props,
      })
      return c.json({ message: 'Model created' })
    },
  )
  .post('/updateModel',
    zValidator('json', adminModelSchema.partial().extend({ id: z.string() })),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const { id, ...updates } = c.req.valid('json')
      await db.update(model).set(updates).where(and(
        eq(model.id, id),
        eq(model.entityId, PUBLIC_ROOT_ID),
      ))
      return c.json({ message: 'Model updated' })
    },
  )
  .post('/deleteModel',
    zValidator('json', z.object({ id: z.string() })),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const { id } = c.req.valid('json')
      await db.delete(model).where(and(
        eq(model.id, id),
        eq(model.entityId, PUBLIC_ROOT_ID),
      ))
      return c.json({ message: 'Model deleted' })
    },
  )
  .post('/updateWorkspace',
    zValidator('json', z.object({
      id: z.string(),
      name: z.string().optional(),
      planId: z.string().optional(),
    })),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const { id, ...updates } = c.req.valid('json')
      await db.update(workspace).set(updates).where(eq(workspace.id, id))
      return c.json({ message: 'Workspace updated' })
    },
  )
  .post('/deleteWorkspace',
    zValidator('json', z.object({ id: z.string() })),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const { id } = c.req.valid('json')
      await db.delete(workspace).where(eq(workspace.id, id))
      return c.json({ message: 'Workspace deleted' })
    },
  )
  .post('/updateGlobalSettings',
    zValidator('json', createUpdateSchema(globalSettings)
      .omit({ oauthProviders: true, searchEngines: true })
      .required({ id: true })),
    async c => {
      const session = await getSession(c.req.raw.headers)
      if (!session || !session.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin')) return c.json({ error: 'Unauthorized' }, 401)
      const { id, ...updates } = c.req.valid('json')
      await db.update(globalSettings).set(updates).where(eq(globalSettings.id, id))
      return c.json({ message: 'Global settings updated' })
    },
  )

export default app
