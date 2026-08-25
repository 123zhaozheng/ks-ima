import { privatePythonOrigin } from '../utils/config'

type Workflow = 'grounded_ask' | 'title_generation' | 'summarization' | 'embedding' | 'reranking'
type Operation = 'chat' | 'embedding' | 'rerank'

export type ManagedResolution = {
  source: 'target' | 'denied' | 'unmigrated'
  workflow: Workflow
  profileId?: string
  profileVersion?: number
  bindingId?: string
  reason?: string
}

const timeoutMs = () => Math.max(250, Number(process.env.IMA_BRIDGE_TIMEOUT_MS ?? 1500))
function internalUrl(path: string) {
  const base = privatePythonOrigin()
  return base ? `${base.replace(/\/$/, '')}/api/v1/internal/model-governance/${path}` : null
}

async function bridge(path: string, body: object): Promise<Response | null> {
  const url = internalUrl(path)
  const token = process.env.IMA_BRIDGE_TOKEN
  if (!url || !token) return null
  try {
    return await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', 'x-ima-bridge-token': token },
      body: JSON.stringify(body),
      redirect: 'error',
      signal: AbortSignal.timeout(timeoutMs()),
    })
  } catch {
    return null
  }
}

/** Metadata-only status. It never contains a URL, remote model or credential. */
export async function resolveManagedStatus(
  workspaceId: string,
  workflow: Workflow,
  operation: Operation,
): Promise<ManagedResolution> {
  const response = await bridge('resolve', { workspaceId, workflow, operation })
  if (!response) return { source: 'denied', workflow, reason: 'BRIDGE_UNAVAILABLE' }
  if (!response.ok) return { source: 'denied', workflow, reason: 'BRIDGE_ERROR' }
  const body = await response.json() as Omit<ManagedResolution, 'source'> & { source?: string, reason?: string }
  if (body.source === 'target' && typeof body.bindingId === 'string' && body.bindingId.length > 0) return { ...body, source: 'target', workflow }
  if (body.source === 'target') return { source: 'denied', workflow, reason: 'MALFORMED_RESPONSE' }
  if (body.source === 'denied' && body.reason === 'NO_ASSIGNMENT') return { ...body, source: 'unmigrated', workflow }
  return { ...body, source: 'denied', workflow, reason: body.reason ?? 'UNAVAILABLE' }
}

export type ManagedChatResult = { kind: 'target' | 'unmigrated' | 'denied', response: Response | null, reason?: string }

export async function executeManagedChat(
  workspaceId: string,
  workflow: Extract<Workflow, 'grounded_ask' | 'title_generation' | 'summarization'>,
  messages: Array<Record<string, unknown>>,
  tools?: Array<Record<string, unknown>>,
  stream = false,
): Promise<ManagedChatResult> {
  const status = await resolveManagedStatus(workspaceId, workflow, 'chat')
  if (status.source !== 'target') return { kind: status.source, response: null, reason: status.reason }
  const response = await bridge('execute/chat', { workspaceId, workflow, messages, tools, stream })
  if (!response) return { kind: 'denied', response: null, reason: 'BRIDGE_UNAVAILABLE' }
  return { kind: 'target', response }
}

export async function executeManagedLegacyChat(
  workspaceId: string,
  workflow: Extract<Workflow, 'grounded_ask' | 'title_generation' | 'summarization'>,
  messages: Array<Record<string, unknown>>,
  tools?: Array<Record<string, unknown>>,
  stream = false,
): Promise<ManagedChatResult> {
  const status = await resolveManagedStatus(workspaceId, workflow, 'chat')
  if (status.source !== 'unmigrated') return { kind: 'denied', response: null, reason: status.reason }
  const response = await bridge('execute/legacy/chat', { workspaceId, workflow, messages, tools, stream })
  if (!response) return { kind: 'denied', response: null, reason: 'BRIDGE_UNAVAILABLE' }
  return { kind: 'unmigrated', response }
}

export async function executeManagedEmbedding(
  workspaceId: string,
  inputs: string[],
): Promise<{ kind: 'target' | 'unmigrated' | 'denied', vectors?: number[][], reason?: string }> {
  const status = await resolveManagedStatus(workspaceId, 'embedding', 'embedding')
  if (status.source !== 'target') return { kind: status.source, reason: status.reason }
  const response = await bridge('execute/embedding', { workspaceId, inputs })
  if (!response) return { kind: 'denied', reason: 'BRIDGE_UNAVAILABLE' }
  if (!response.ok) return { kind: 'denied', reason: 'EXECUTION_FAILED' }
  const body = await response.json() as { vectors?: number[][] }
  if (!Array.isArray(body.vectors) || body.vectors.length !== inputs.length || body.vectors.some(vector => !Array.isArray(vector) || vector.length === 0 || vector.some(value => typeof value !== 'number' || !Number.isFinite(value)))) return { kind: 'denied', reason: 'MALFORMED_RESPONSE' }
  return { kind: 'target', vectors: body.vectors }
}

export async function executeManagedLegacyEmbedding(
  workspaceId: string,
  inputs: string[],
): Promise<{ kind: 'unmigrated' | 'denied', vectors?: number[][], reason?: string }> {
  const status = await resolveManagedStatus(workspaceId, 'embedding', 'embedding')
  if (status.source !== 'unmigrated') return { kind: 'denied', reason: status.reason }
  const response = await bridge('execute/legacy/embedding', { workspaceId, inputs })
  if (!response) return { kind: 'denied', reason: 'BRIDGE_UNAVAILABLE' }
  if (!response.ok) return { kind: 'denied', reason: 'EXECUTION_FAILED' }
  const body = await response.json() as { vectors?: number[][] }
  if (!Array.isArray(body.vectors) || body.vectors.length !== inputs.length || body.vectors.some(vector => !Array.isArray(vector) || vector.length === 0 || vector.some(value => typeof value !== 'number' || !Number.isFinite(value)))) return { kind: 'denied', reason: 'MALFORMED_RESPONSE' }
  return { kind: 'unmigrated', vectors: body.vectors }
}

export async function executeManagedRerank(
  workspaceId: string,
  query: string,
  documents: string[],
): Promise<{ kind: 'target' | 'unmigrated' | 'denied', results?: Array<{ index: number, relevance_score: number }>, reason?: string }> {
  const status = await resolveManagedStatus(workspaceId, 'reranking', 'rerank')
  if (status.source !== 'target') return { kind: status.source, reason: status.reason }
  const response = await bridge('execute/rerank', { workspaceId, query, documents })
  if (!response) return { kind: 'denied', reason: 'BRIDGE_UNAVAILABLE' }
  if (!response.ok) return { kind: 'denied', reason: 'EXECUTION_FAILED' }
  const body = await response.json() as { results?: Array<{ index: number, relevance_score: number }> }
  if (!Array.isArray(body.results) || body.results.some(item => !Number.isInteger(item.index) || item.index < 0 || item.index >= documents.length || !Number.isFinite(item.relevance_score))) return { kind: 'denied', reason: 'MALFORMED_RESPONSE' }
  return { kind: 'target', results: body.results }
}

export async function executeManagedLegacyRerank(
  workspaceId: string,
  query: string,
  documents: string[],
): Promise<{ kind: 'unmigrated' | 'denied', results?: Array<{ index: number, relevance_score: number }>, reason?: string }> {
  const status = await resolveManagedStatus(workspaceId, 'reranking', 'rerank')
  if (status.source !== 'unmigrated') return { kind: 'denied', reason: status.reason }
  const response = await bridge('execute/legacy/rerank', { workspaceId, query, documents })
  if (!response) return { kind: 'denied', reason: 'BRIDGE_UNAVAILABLE' }
  if (!response.ok) return { kind: 'denied', reason: 'EXECUTION_FAILED' }
  const body = await response.json() as { results?: Array<{ index: number, relevance_score: number }> }
  if (!Array.isArray(body.results) || body.results.some(item => !Number.isInteger(item.index) || item.index < 0 || item.index >= documents.length || !Number.isFinite(item.relevance_score))) return { kind: 'denied', reason: 'MALFORMED_RESPONSE' }
  return { kind: 'unmigrated', results: body.results }
}
