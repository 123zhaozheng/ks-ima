import { Hono } from 'hono'
import { logger } from 'hono/logger'
import zero from './zero/routes'
import s3 from './s3'
import ai from './ai'
import { seed } from './utils/seed'
import admin from './admin'
import search from './search'
import kb from './kb'
import mcp from './mcp'
import connectors from './connectors'
import { initJobs } from './jobs'
import { sizeBytes } from 'app/src-shared/utils/functions'
import { log } from './utils/functions'

seed()
initJobs()

export const app = new Hono().basePath('/api')
  .use(logger(log))
  .route('/zero', zero)
  .route('/s3', s3)
  .route('/v1', ai)
  .route('/admin', admin)
  .route('/search', search)
  .route('/kb', kb)
  .route('/mcp', mcp)
  .route('/connectors', connectors)

export default {
  fetch: app.fetch,
  maxRequestBodySize: sizeBytes('5G'),
  idleTimeout: 0,
}

export type AppType = typeof app
