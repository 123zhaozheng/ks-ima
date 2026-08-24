import { addMonths } from 'date-fns'
import { workspace } from '../schema'
import { db } from '../utils/db'
import { eq } from 'drizzle-orm'

export async function resetQuota() {
  await db.transaction(async tx => {
    const workspaces = await tx.query.workspace.findMany({
      where: {
        resetAt: { lte: new Date() },
      },
    })
    for (const ws of workspaces) {
      await tx.update(workspace).set({
        quotaUsed: 0,
        resetAt: addMonths(ws.resetAt, 1),
      }).where(eq(workspace.id, ws.id))
    }
  })
}
