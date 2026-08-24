/**
 * Local Postgres without Docker Desktop.
 * Matches DATABASE_URL (default 127.0.0.1:5430) using embedded-postgres.
 * https://github.com/leinelissen/embedded-postgres
 */
import EmbeddedPostgres from 'embedded-postgres'
import { existsSync, mkdirSync } from 'node:fs'

const databaseUrl = process.env.DATABASE_URL || 'postgres://user:password@127.0.0.1:5430/app'
const parsed = new URL(databaseUrl.replace(/^postgres(ql)?:/, 'http:'))
const port = Number(parsed.port || 5430)
const user = decodeURIComponent(parsed.username || 'user')
const password = decodeURIComponent(parsed.password || 'password')
const appDb = decodeURIComponent((parsed.pathname || '/app').replace(/^\//, '') || 'app')

mkdirSync('.dev-pg', { recursive: true })

const pg = new EmbeddedPostgres({
  databaseDir: '.dev-pg/data',
  user,
  password,
  port,
  persistent: true,
  postgresFlags: [
    '-c', 'wal_level=logical',
    '-c', 'max_wal_senders=10',
    '-c', 'max_replication_slots=5',
    '-c', 'hot_standby=on',
  ],
})

if (!existsSync('.dev-pg/data/PG_VERSION')) {
  await pg.initialise()
}

await pg.start()

for (const name of [appDb, 'zero', 'postgres']) {
  try {
    await pg.createDatabase(name)
  } catch {
    // already exists
  }
}

console.log(`postgres listening on 127.0.0.1:${port} (db ${appDb})`)

await new Promise(() => {})
