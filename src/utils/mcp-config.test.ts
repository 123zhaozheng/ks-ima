import { describe, expect, test } from 'bun:test'
import { cursorMcpConfig, mcpHttpUrl } from './mcp-config'

describe('legacy MCP connector configuration', () => {
  test('keeps legacy keys on the coexistence endpoint', () => {
    expect(mcpHttpUrl('https://ima.example/')).toBe('https://ima.example/api/mcp')
    expect(cursorMcpConfig('ima_example', 'https://ima.example')).toEqual({
      mcpServers: {
        'intranet-ima': {
          url: 'https://ima.example/api/mcp',
          headers: { Authorization: 'Bearer ima_example' },
        },
      },
    })
  })
})
