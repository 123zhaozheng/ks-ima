import { DEFAULT_PLAN_ID, PUBLIC_ROOT_ID } from 'app/src-shared/utils/config'
import { db } from './db'
import { entity, globalSettings, plan, provider } from '../schema'
import { entityDefaultProps } from 'app/src-shared/mutators'
import { sizeBytes } from 'app/src-shared/utils/functions'
import { sql } from 'drizzle-orm'

export async function seed() {
  await db.execute(sql`
    CREATE TABLE IF NOT EXISTS "connector" (
      "id" varchar(16) PRIMARY KEY NOT NULL,
      "workspaceId" varchar(16) NOT NULL REFERENCES "workspace"("id") ON DELETE cascade,
      "createdBy" text NOT NULL REFERENCES "user"("id") ON DELETE cascade,
      "name" text NOT NULL,
      "note" text,
      "keyHash" text NOT NULL,
      "keyPrefix" text NOT NULL,
      "mode" text NOT NULL,
      "folderRootId" varchar(16) REFERENCES "entity"("id") ON DELETE set null,
      "expiresAt" timestamp,
      "revokedAt" timestamp,
      "lastUsedAt" timestamp,
      "createdAt" timestamp NOT NULL
    )
  `)
  await db.execute(sql`CREATE INDEX IF NOT EXISTS "connector_workspaceId_index" ON "connector" ("workspaceId")`)
  await db.execute(sql`CREATE INDEX IF NOT EXISTS "connector_keyHash_index" ON "connector" ("keyHash")`)
  await db.insert(globalSettings).values({
    id: 'default',
    freeModelReqLimit: 60,
    freeModelLimitWindow: 3600 * 1000,
    maxWorkspacesPerUser: 10,
    searchEngines: 'brave',
    oauthProviders: [],
  }).onConflictDoNothing()
  await db.insert(plan).values({
    id: DEFAULT_PLAN_ID,
    name: 'Default',
    maxMembers: 10,
    storageLimit: sizeBytes('1T'),
    fileSizeLimit: sizeBytes('5G'),
    quotaLimit: 10,
  }).onConflictDoNothing()
  await db.insert(entity).values({
    ...entityDefaultProps,
    id: PUBLIC_ROOT_ID,
    rootId: PUBLIC_ROOT_ID,
    parentId: null,
    type: 'folder',
    name: 'Public',
  }).onConflictDoNothing()
  await db.insert(provider).values({
    id: PUBLIC_ROOT_ID,
    rootId: PUBLIC_ROOT_ID,
    type: 'openaiCompatible',
    settings: {
      baseURL: '/api/v1',
    },
  }).onConflictDoNothing()
}
