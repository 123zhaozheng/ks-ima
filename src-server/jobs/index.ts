import { Cron } from 'croner'
import { resetQuota } from './reset-quota'
import { cleanBlobs } from './clean-blobs'
import { parseKb } from './parse-kb'
import { log } from '../utils/functions'

const g = globalThis as typeof globalThis & { __nyaJobs?: Record<string, Cron> }

function wrapJob(fn: () => Promise<void>) {
  return async function() {
    log(`Running job: ${fn.name}`)
    await fn()
    log(`Finished job: ${fn.name}`)
  }
}

export function initJobs() {
  if (g.__nyaJobs) {
    for (const job of Object.values(g.__nyaJobs)) job.stop()
  }
  g.__nyaJobs = {
    resetQuota: new Cron('10 */5 * * * *', { protect: true }, wrapJob(resetQuota)),
    cleanBlobs: new Cron('20 0 * * * *', { protect: true }, wrapJob(cleanBlobs)),
    parseKb: new Cron('*/15 * * * * *', { protect: true }, wrapJob(parseKb)),
  }
  return g.__nyaJobs
}
