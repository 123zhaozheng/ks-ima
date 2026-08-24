import { parseQueuedItems } from '../kb/ingest'
import { log } from '../utils/functions'

export async function parseKb() {
  try {
    await parseQueuedItems()
  } catch (err) {
    log(`parseKb: ${err instanceof Error ? err.message : String(err)}`)
  }
}
