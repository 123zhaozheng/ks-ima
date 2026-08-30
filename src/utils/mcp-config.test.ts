import { describe, expect, test } from 'bun:test'
import { cursorMcpConfig, mcpHttpUrl } from './mcp-config'

describe('MCP connector configuration', () => {
  test('points agent configs at the canonical /mcp endpoint', () => {
    expect(mcpHttpUrl('https://ima.example/')).toBe('https://ima.example/mcp')
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
