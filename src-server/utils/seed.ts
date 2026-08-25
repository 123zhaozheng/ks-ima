import { PUBLIC_ROOT_ID } from 'app/src-shared/utils/config'
import { db } from './db'
import { entity } from '../schema'
import { entityDefaultProps } from 'app/src-shared/mutators'
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
  await db.execute(sql`
    DO $$ BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'globalSettings' AND column_name = 'embeddingModelId'
      ) THEN
        ALTER TABLE "globalSettings" ADD COLUMN "embeddingModelId" varchar(16) REFERENCES "model"("id") ON DELETE set null;
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'globalSettings' AND column_name = 'rerankModelId'
      ) THEN
        ALTER TABLE "globalSettings" ADD COLUMN "rerankModelId" varchar(16) REFERENCES "model"("id") ON DELETE set null;
      END IF;
      IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'chunk'
      ) THEN
        CREATE TABLE "chunk" (
          "id" varchar(16) PRIMARY KEY NOT NULL,
          "rootId" varchar(16) NOT NULL,
          "entityId" varchar(16) NOT NULL REFERENCES "entity"("id") ON DELETE cascade,
          "ordinal" integer NOT NULL,
          "text" text NOT NULL,
          "page" integer,
          "embedding" jsonb,
          "search" tsvector GENERATED ALWAYS AS (to_tsvector('mixed', left("text", 250000))) STORED
        );
        CREATE INDEX "chunk_entityId_index" ON "chunk" ("entityId");
        CREATE INDEX "chunk_rootId_index" ON "chunk" ("rootId");
        CREATE INDEX "chunk_search_index" ON "chunk" USING GIN ("search");
      END IF;
    END $$
  `)
  await db.insert(entity).values({
    ...entityDefaultProps,
    id: PUBLIC_ROOT_ID,
    rootId: PUBLIC_ROOT_ID,
    parentId: null,
    type: 'folder',
    name: 'Public',
  }).onConflictDoNothing()
}
