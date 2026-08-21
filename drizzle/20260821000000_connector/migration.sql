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
);
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "connector_workspaceId_index" ON "connector" ("workspaceId");
--> statement-breakpoint
CREATE INDEX IF NOT EXISTS "connector_keyHash_index" ON "connector" ("keyHash");
