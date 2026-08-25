import { executeManagedEmbedding, executeManagedLegacyEmbedding } from './model-governance'
import { log } from '../utils/functions'

export async function embedTexts(texts: string[], workspaceId: string): Promise<number[][] | null> {
  if (!texts.length) return []
  const managed = await executeManagedEmbedding(workspaceId, texts)
  if (managed.kind === 'target') return managed.vectors ?? null
  if (managed.kind === 'denied') return null
  const legacy = await executeManagedLegacyEmbedding(workspaceId, texts)
  return legacy.kind === 'unmigrated' ? legacy.vectors ?? null : null
}

export async function embedQuery(q: string, workspaceId: string): Promise<number[] | null> {
  const rows = await embedTexts([q], workspaceId)
  if (!rows) return null
  return rows[0] ?? null
}

export function cosine(a: number[], b: number[]) {
  let dot = 0
  let na = 0
  let nb = 0
  const n = Math.min(a.length, b.length)
  for (let i = 0; i < n; i++) {
    dot += a[i] * b[i]
    na += a[i] * a[i]
    nb += b[i] * b[i]
  }
  if (!na || !nb) return 0
  return dot / Math.sqrt(na * nb)
}

export async function safeEmbedTexts(texts: string[], workspaceId: string) {
  try {
    return await embedTexts(texts, workspaceId)
  } catch (err) {
    log(`embedTexts failed: ${String(err)}`)
    return null
  }
}
