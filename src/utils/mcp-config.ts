export function mcpAgentOrigin(browserOrigin = window.location.origin) {
  try {
    const url = new URL(browserOrigin)
    // Cursor/Claude are native clients. Vite :9015 is a browser proxy; talk to Hono.
    if (url.port === '9015' || url.port === '9016') url.port = '3000'
    // Windows often resolves localhost to ::1 while the API listens on IPv4.
    if (url.hostname === 'localhost') url.hostname = '127.0.0.1'
    return url.origin
  } catch {
    return browserOrigin
  }
}

export function mcpHttpUrl(origin = mcpAgentOrigin()) {
  return `${origin.replace(/\/$/, '')}/api/mcp`
}

export function cursorMcpConfig(apiKey: string, origin = mcpAgentOrigin()) {
  return {
    mcpServers: {
      'intranet-ima': {
        url: mcpHttpUrl(origin),
        headers: {
          Authorization: `Bearer ${apiKey}`,
        },
      },
    },
  }
}

/** Claude Desktop still speaks stdio; mcp-remote is the thin local bridge. */
export function claudeDesktopMcpConfig(apiKey: string, origin = mcpAgentOrigin()) {
  return {
    mcpServers: {
      'intranet-ima': {
        command: 'npx',
        args: [
          '-y',
          'mcp-remote',
          mcpHttpUrl(origin),
          '--allow-http',
          '--header',
          'Authorization:' + '$' + '{IMA_MCP_AUTH}',
        ],
        env: {
          IMA_MCP_AUTH: `Bearer ${apiKey}`,
        },
      },
    },
  }
}

export function prettyJson(value: unknown) {
  return JSON.stringify(value, null, 2)
}

/** Same handshake Cursor uses: initialize then tools/list. */
async function probeOne(apiKey: string, url: string) {
  async function rpc(method: string, params: unknown, id: number) {
    const res = await fetch(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'application/json, text/event-stream',
        authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ jsonrpc: '2.0', id, method, params }),
    })
    const text = await res.text()
    let body: { result?: { tools?: Array<{ name: string }> }, error?: { message?: string } }
    try {
      body = JSON.parse(text)
    } catch {
      throw new Error(`${res.status} ${text.slice(0, 180)}`)
    }
    if (!res.ok || body.error) {
      throw new Error(body.error?.message || `${res.status} ${text.slice(0, 180)}`)
    }
    return body
  }

  await rpc('initialize', {
    protocolVersion: '2025-03-26',
    capabilities: {},
    clientInfo: { name: 'intranet-ima-ui', version: '1.0.0' },
  }, 1)
  const listed = await rpc('tools/list', {}, 2)
  return {
    ok: true as const,
    url,
    tools: listed.result?.tools?.map(tool => tool.name) ?? [],
  }
}

export async function probeMcpConnection(apiKey: string, preferred = mcpHttpUrl()) {
  const urls = [...new Set([
    preferred,
    `${window.location.origin.replace(/\/$/, '')}/api/mcp`,
  ])]
  let last: Error | undefined
  for (const url of urls) {
    try {
      return await probeOne(apiKey, url)
    } catch (err) {
      last = err instanceof Error ? err : new Error(String(err))
    }
  }
  throw last ?? new Error('MCP unreachable')
}
