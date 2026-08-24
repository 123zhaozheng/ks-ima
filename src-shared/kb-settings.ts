export const KB_SEARCH_MODES = ['keyword', 'hybrid', 'vector'] as const
export type KbSearchMode = (typeof KB_SEARCH_MODES)[number]

export function parseKbSearchMode(value: unknown): KbSearchMode {
  if (value === 'keyword' || value === 'hybrid' || value === 'vector') return value
  return 'hybrid'
}

/** Dify/RAGFlow-style top_k. Default 8. */
export function parseKbTopK(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 8
  return Math.min(30, Math.max(1, Math.round(n)))
}

/** Drop passages below this score after fusion/rerank. 0 keeps all. */
export function parseKbScoreThreshold(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.min(1, n)
}

/** Dify hybrid default: vector 0.7 / keyword 0.3. */
export function parseKbVectorWeight(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0.7
  return Math.min(1, Math.max(0, n))
}

/** Open WebUI CHUNK_SIZE style. Default 600, range 200–2000. */
export function parseKbChunkSize(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 600
  return Math.min(2000, Math.max(200, Math.round(n)))
}

/** Open WebUI CHUNK_OVERLAP style. Default 80, range 0–500. */
export function parseKbChunkOverlap(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 80
  return Math.min(500, Math.max(0, Math.round(n)))
}

function unit(n: number) {
  return Math.max(0, Math.min(1, n))
}

/** Dify `weighted_score`: vector_weight * cosine + keyword_weight * keyword. */
export function weightedHybridScore(
  fts: number | undefined,
  vec: number | undefined,
  vectorWeight: number,
) {
  return vectorWeight * unit(vec ?? 0) + (1 - vectorWeight) * unit(fts ?? 0)
}

/** Split text into chunks honoring configurable size/overlap (Open WebUI style). */
export function chunkText(text: string, target = 600, overlap = 80): string[] {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (!normalized) return []
  const parts = normalized.split(/\n{2,}/).map(p => p.trim()).filter(Boolean)
  const chunks: string[] = []
  let buf = ''
  for (const part of parts) {
    if (part.length > target * 2) {
      if (buf) {
        chunks.push(buf)
        buf = ''
      }
      for (const piece of splitLong(part, target, overlap)) chunks.push(piece)
      continue
    }
    if (!buf) {
      buf = part
      continue
    }
    if (buf.length + 2 + part.length <= target * 1.4) {
      buf = `${buf}\n\n${part}`
    } else {
      chunks.push(buf)
      buf = overlapFrom(buf, overlap) + part
    }
  }
  if (buf.trim()) chunks.push(buf)
  return chunks
}

function splitLong(text: string, target: number, overlap: number) {
  const out: string[] = []
  let i = 0
  while (i < text.length) {
    const end = Math.min(text.length, i + target)
    out.push(text.slice(i, end))
    if (end >= text.length) break
    i = Math.max(0, end - overlap)
  }
  return out
}

function overlapFrom(text: string, overlap: number) {
  if (text.length <= overlap) return `${text}\n\n`
  return `${text.slice(-overlap)}\n\n`
}
