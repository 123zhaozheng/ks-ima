import { describe, expect, it, vi } from 'vitest'
import { knowledgeClient } from 'src/api/knowledge-client'

vi.mock('src/api/ima-client', () => ({
  imaClient: { request: vi.fn().mockResolvedValue({}) },
}))

describe('knowledge file client', () => {
  it('uses target upload and ingestion routes', async () => {
    await knowledgeClient.uploadTicket('folder id', {
      title: 'report.txt', filename: 'report.txt', mimeType: 'text/plain', sizeBytes: 4, checksum: 'a'.repeat(64),
    })
    await knowledgeClient.completeUpload('document id', 'ticket')
    await knowledgeClient.retryIngestion('document id')
    await knowledgeClient.cancelIngestion('document id')
    await knowledgeClient.replacementUploadTicket('document id', {
      title: 'next.txt', filename: 'next.txt', mimeType: 'text/plain', sizeBytes: 4, checksum: 'a'.repeat(64), expectedVersion: 1, expectedContentVersion: 1,
    })
    await knowledgeClient.fileVersions('document id')
    const { imaClient } = await import('src/api/ima-client')
    const paths = (imaClient.request as ReturnType<typeof vi.fn>).mock.calls.map(([path]) => path)
    expect(paths).toContain('/api/v1/folders/folder%20id/files/upload-ticket')
    expect(paths).toContain('/api/v1/documents/document%20id/file-versions/complete')
    expect(paths).toContain('/api/v1/documents/document%20id/ingestion/retry')
    expect(paths).toContain('/api/v1/documents/document%20id/ingestion/cancel')
    expect(paths).toContain('/api/v1/documents/document%20id/file-versions/upload-ticket')
    expect(paths).toContain('/api/v1/documents/document%20id/file-versions')
  })
})
