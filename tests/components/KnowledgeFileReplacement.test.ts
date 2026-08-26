import { describe, expect, it, vi } from 'vitest'
import { knowledgeClient } from 'src/api/knowledge-client'

vi.mock('src/api/ima-client', () => ({
  imaClient: { request: vi.fn().mockResolvedValue({ items: [] }) },
}))

describe('knowledge file replacement client', () => {
  it('uses expected-version ticket and immutable history routes', async () => {
    await knowledgeClient.replacementUploadTicket('file-1', {
      title: 'updated.txt', filename: 'updated.txt', mimeType: 'text/plain', sizeBytes: 7,
      checksum: 'a'.repeat(64), expectedVersion: 2, expectedContentVersion: 1,
    })
    await knowledgeClient.fileVersions('file-1')
    const { imaClient } = await import('src/api/ima-client')
    const calls = (imaClient.request as ReturnType<typeof vi.fn>).mock.calls
    expect(calls[0][0]).toBe('/api/v1/documents/file-1/file-versions/upload-ticket')
    expect(JSON.parse(calls[0][1]?.body as string)).toMatchObject({ expectedVersion: 2, expectedContentVersion: 1 })
    expect(calls[1][0]).toBe('/api/v1/documents/file-1/file-versions')
  })
})
