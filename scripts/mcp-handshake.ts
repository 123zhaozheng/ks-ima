/**
 * Protocol handshake for the MCP module (no database).
 * Uses the official SDK client (same stack as Cursor) against an in-process Streamable HTTP server.
 */
import { Client } from '@modelcontextprotocol/sdk/client/index.js'
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js'
import { dispatchMcp, type McpActor } from '../src-server/mcp-dispatch'

const readActor: McpActor = {
  userId: 'smoke',
  role: 'owner',
  workspaceId: 'ws_smoke',
  mode: 'read',
}

const bunServer = Bun.serve({
  port: 0,
  async fetch(req) {
    const url = new URL(req.url)
    if (url.pathname !== '/api/mcp') return new Response('not found', { status: 404 })
    if (req.headers.get('authorization') !== 'Bearer ima_smoke') {
      return Response.json({ error: 'Unauthorized' }, { status: 401 })
    }
    return dispatchMcp(readActor, req, async (name, args) => ({
      content: [{ type: 'text', text: JSON.stringify({ tool: name, args }) }],
    }))
  },
})

const url = `http://127.0.0.1:${bunServer.port}/api/mcp`
const client = new Client({ name: 'intranet-ima-smoke', version: '0' })
const transport = new StreamableHTTPClientTransport(new URL(url), {
  requestInit: {
    headers: { Authorization: 'Bearer ima_smoke' },
  },
})

try {
  await client.connect(transport)
  const { tools } = await client.listTools()
  const names = tools.map(t => t.name)
  const need = ['kb_search', 'kb_ask', 'kb_list_dir', 'kb_get_tree']
  const missing = need.filter(n => !names.includes(n))
  const writeHidden = names.includes('kb_mkdir')
  const called = await client.callTool({ name: 'kb_search', arguments: { q: '制度' } })
  const text = JSON.stringify(called)
  const asked = await client.callTool({
    name: 'kb_ask',
    arguments: { question: '制度', folderId: 'folder_smoke', tags: ['hr'] },
  })
  const askedText = JSON.stringify(asked)

  console.log(JSON.stringify({
    url,
    connected: true,
    names,
    missing,
    writeHidden,
    searchCallOk: text.includes('kb_search'),
    askCallOk: askedText.includes('kb_ask') && askedText.includes('folder_smoke'),
  }, null, 2))

  if (missing.length || writeHidden || !text.includes('kb_search') || !askedText.includes('folder_smoke')) process.exit(1)
} finally {
  await client.close().catch(() => {})
  bunServer.stop(true)
}
