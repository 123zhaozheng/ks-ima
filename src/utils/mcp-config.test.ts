import { describe, expect, test } from 'bun:test'
import { cursorMcpConfig, mcpAgentOrigin, mcpHttpUrl } from './mcp-config'

describe('MCP connector configuration', () => {
  test('points agent configs at the canonical /mcp endpoint', () => {
    expect(mcpHttpUrl('https://ima.example/')).toBe('https://ima.example/mcp')
    // Dev pages are served on 9015 with the API on 9016; the MCP link must
    // point at the API (the old code's port 3000 has no listener).
    expect(mcpAgentOrigin('http://localhost:9015')).toBe('http://127.0.0.1:9016')
    expect(cursorMcpConfig('ima_example', 'https://ima.example')).toEqual({
      mcpServers: {
        'intranet-ima': {
          url: 'https://ima.example/mcp',
          headers: { Authorization: 'Bearer ima_example' },
        },
      },
    })
  })
})
