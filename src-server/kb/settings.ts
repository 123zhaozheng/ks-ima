import { db } from '../utils/db'
import { getGlobalSettings } from '../utils/settings'
import {
  parseKbChunkOverlap,
  parseKbChunkSize,
  parseKbScoreThreshold,
  parseKbSearchMode,
  parseKbTopK,
  parseKbVectorWeight,
  type KbSearchMode,
} from 'app/src-shared/kb-settings'

export async function workspaceKbSettings(workspaceId: string): Promise<{
  embeddingModelId: string | null
  rerankModelId: string | null
  searchMode: KbSearchMode
  topK: number
  scoreThreshold: number
  vectorWeight: number
  chunkSize: number
  chunkOverlap: number
}> {
  const [ws, g] = await Promise.all([
    db.query.workspace.findFirst({ where: { id: workspaceId } }),
    getGlobalSettings(),
  ])
  const p = (ws?.perfs ?? {}) as Record<string, unknown>
  return {
    embeddingModelId: (typeof p.embeddingModelId === 'string' && p.embeddingModelId) || g.embeddingModelId || null,
    rerankModelId: (typeof p.rerankModelId === 'string' && p.rerankModelId) || g.rerankModelId || null,
    searchMode: parseKbSearchMode(p.kbSearchMode),
    topK: parseKbTopK(p.kbTopK),
    scoreThreshold: parseKbScoreThreshold(p.kbScoreThreshold),
    vectorWeight: parseKbVectorWeight(p.kbVectorWeight),
    chunkSize: parseKbChunkSize(p.kbChunkSize),
    chunkOverlap: parseKbChunkOverlap(p.kbChunkOverlap),
  }
}
