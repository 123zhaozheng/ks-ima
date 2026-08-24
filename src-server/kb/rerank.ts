import { rerankGateway } from './models'
import { log } from '../utils/functions'

export async function rerank(query: string, documents: string[], workspaceId: string): Promise<number[] | null> {
  if (!documents.length) return []
  const gateway = await rerankGateway(workspaceId)
  if (!gateway) return null
  try {
    const tei = await tryJson(`${gateway.baseURL}/rerank`, gateway.apiKey, {
      query,
      texts: documents,
      raw_scores: false,
    })
    if (Array.isArray(tei)) {
      return scoresFromTei(tei, documents.length)
    }
    const jina = await tryJson(`${gateway.baseURL}/v1/rerank`, gateway.apiKey, {
      model: gateway.name,
      query,
      documents,
    })
    if (jina?.results) {
      return scoresFromJina(jina.results, documents.length)
    }
  } catch (err) {
    log(`rerank failed: ${String(err)}`)
  }
  return null
}

async function tryJson(url: string, apiKey: string, body: object) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) return null
  return res.json()
}

function scoresFromTei(rows: { index?: number, score?: number }[], length: number) {
  const scores = Array.from({ length }, () => 0)
  for (const row of rows) {
    if (typeof row.index === 'number' && typeof row.score === 'number') scores[row.index] = row.score
  }
  return scores
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
