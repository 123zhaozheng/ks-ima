import { executeManagedLegacyRerank, executeManagedRerank } from './model-governance'
import { log } from '../utils/functions'

export async function rerank(query: string, documents: string[], workspaceId: string): Promise<number[] | null> {
  if (!documents.length) return []
  const managed = await executeManagedRerank(workspaceId, query, documents)
  if (managed.kind === 'target') {
    return managed.results ? scoresFromJina(managed.results, documents.length) : null
  }
  if (managed.kind === 'denied') return null
  try {
    const legacy = await executeManagedLegacyRerank(workspaceId, query, documents)
    if (legacy.kind === 'unmigrated' && legacy.results) return scoresFromJina(legacy.results, documents.length)
  } catch (err) {
    log(`rerank failed: ${String(err)}`)
  }
  return null
}

function scoresFromJina(rows: { index?: number, relevance_score?: number }[], length: number) {
  const scores = Array.from({ length }, () => 0)
  for (const row of rows) {
    if (typeof row.index === 'number' && typeof row.relevance_score === 'number') {
      scores[row.index] = row.relevance_score
    }
  }
  return scores
}
