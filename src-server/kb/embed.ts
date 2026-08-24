import { embeddingGateway, type GatewayModel } from './models'
import { log } from '../utils/functions'

async function embedBatch(gateway: GatewayModel, inputs: string[]) {
  const res = await fetch(`${gateway.baseURL}/embeddings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${gateway.apiKey}`,
    },
    body: JSON.stringify({
      model: gateway.name,
      input: inputs,
    }),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`Embedding gateway ${res.status}: ${body.slice(0, 400)}`)
  }
  const json = await res.json() as { data?: { embedding: number[], index: number }[] }
  const data = [...(json.data ?? [])].sort((a, b) => a.index - b.index)
  return data.map(d => d.embedding)
}

export async function embedTexts(texts: string[], workspaceId: string): Promise<number[][] | null> {
  if (!texts.length) return []
  const gateway = await embeddingGateway(workspaceId)
  if (!gateway) return null
  const out: number[][] = []
  const size = 16
  for (let i = 0; i < texts.length; i += size) {
    const batch = texts.slice(i, i + size)
    out.push(...await embedBatch(gateway, batch))
  }
  return out
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
