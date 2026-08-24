import 'dotenv/config'
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { eq, inArray, like } from 'drizzle-orm'
import { connector } from '../src-server/schema'
import { db } from '../src-server/utils/db'
import { generateApiKey } from '../src-server/utils/permissions'
import { genId } from '../src-shared/utils/id'

const endpoint = new URL(process.env.MCP_TEST_URL ?? 'http://127.0.0.1:3000/api/mcp')
const connectorIds: string[] = []
await db.delete(connector).where(like(connector.name, '__test__ MCP live %'))

function assert(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message)
}

async function createConnector(mode: 'read' | 'readwrite', expiresAt?: Date) {
  const workspace = await db.query.workspace.findFirst({
    columns: { id: true, ownerId: true },
  })
  assert(workspace, 'Create a workspace before running the live MCP test')
  const key = generateApiKey()
  const id = genId()
  connectorIds.push(id)
  await db.insert(connector).values({
    id,
    workspaceId: workspace.id,
    createdBy: workspace.ownerId,
    name: `__test__ MCP live ${mode}`,
    keyHash: key.hash,
    keyPrefix: key.prefix,
    mode,
    folderRootId: workspace.id,
    expiresAt,
    createdAt: new Date(),
  })
  return { id, raw: key.raw, workspaceId: workspace.id }
}

async function connect(raw: string) {
  const client = new Client({ name: 'intranet-ima-live', version: '1' })
  const transport = new StreamableHTTPClientTransport(endpoint, {
    requestInit: { headers: { Authorization: `Bearer ${raw}` } },
  })
  await client.connect(transport)
  return client
}

async function authStatus(raw: string) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const response = await fetch(endpoint, {
      headers: { Authorization: `Bearer ${raw}` },
      signal: controller.signal,
    })
    return response.status
  } finally {
    clearTimeout(timeout)
  }
}

async function deadline<T>(label: string, promise: Promise<T>, timeoutMs = 10_000): Promise<T> {
  let timeout: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_resolve, reject) => {
        timeout = setTimeout(() => reject(new Error(`${label} timed out`)), timeoutMs)
      }),
    ])
  } finally {
    if (timeout) clearTimeout(timeout)
  }
}

const requiredRead = [
  'kb_list_workspaces', 'kb_list_dir', 'kb_get_tree', 'kb_search',
  'kb_ask', 'kb_get_note', 'kb_get_file', 'kb_list_tags',
]
const requiredWrite = [
  'kb_mkdir', 'kb_create_note', 'kb_update_note', 'kb_upload_file',
  'kb_move', 'kb_set_tags', 'kb_delete',
]

let exitCode = 0
try {
  const read = await createConnector('read')
  const readClient = await deadline('read connect', connect(read.raw))
  const readNames = (await deadline('read tools/list', readClient.listTools())).tools.map(tool => tool.name)
  assert(requiredRead.every(name => readNames.includes(name)), 'Read tool set is incomplete')
  assert(requiredWrite.every(name => !readNames.includes(name)), 'Read key exposed a write tool')

  const crossWorkspace = await deadline('cross-workspace call', readClient.callTool({
    name: 'kb_ask',
    arguments: { workspaceId: 'outside-workspace', question: 'test' },
  }))
  assert(crossWorkspace.isError, 'Cross-workspace ask was not rejected')

  const outsideRoot = await deadline('folder-scope call', readClient.callTool({
    name: 'kb_list_dir',
    arguments: { folderId: 'outside-folder' },
  }))
  assert(JSON.stringify(outsideRoot).includes('Not found'), 'Folder-root scope did not hide an outside ID')
  assert(outsideRoot.isError, 'Folder-root operation error was not marked as an MCP error')

  await db.update(connector).set({ revokedAt: new Date() }).where(eq(connector.id, read.id))
  const revoked = await authStatus(read.raw) === 401
  assert(revoked, 'Revoked key remained usable')

  const write = await createConnector('readwrite')
  const writeClient = await deadline('write connect', connect(write.raw))
  const writeNames = (await deadline('write tools/list', writeClient.listTools())).tools.map(tool => tool.name)
  assert([...requiredRead, ...requiredWrite].every(name => writeNames.includes(name)), 'Read-write tool set is incomplete')

  const expired = await createConnector('read', new Date(Date.now() - 60_000))
  const expirationRejected = await authStatus(expired.raw) === 401
  assert(expirationRejected, 'Expired key connected successfully')

  console.log(JSON.stringify({
    ok: true,
    endpoint: endpoint.toString(),
    readTools: readNames.length,
    writeTools: writeNames.length,
    crossWorkspaceRejected: true,
    folderScopeRejected: true,
    revoked,
    expirationRejected,
  }))
} catch (error) {
  exitCode = 1
  console.error(error)
} finally {
  if (connectorIds.length) {
    await db.delete(connector).where(inArray(connector.id, connectorIds))
  }
}
process.exit(exitCode)
