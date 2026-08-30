import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { knowledgeClient } from 'src/api/knowledge-client'
import { computed } from 'vue'

async function digestFile(file: File, signal?: AbortSignal) {
  const supported = new Set(['text/plain', 'text/markdown', 'application/json', 'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.ms-excel'])
  if (!supported.has(file.type)) throw new Error('Unsupported file type')
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
  const digest = await crypto.subtle.digest('SHA-256', await file.arrayBuffer())
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

function checksumHeader(checksum: string) {
  const bytes = checksum.match(/.{2}/g)!.map(value => Number.parseInt(value, 16))
  return btoa(String.fromCharCode(...bytes))
}

function putWithProgress(url: string, file: File, mimeType: string, checksum: string, onProgress: (value: number) => void, signal?: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const request = new XMLHttpRequest()
    request.open('PUT', url)
    request.setRequestHeader('Content-Type', mimeType)
    request.setRequestHeader('x-amz-checksum-sha256', checksumHeader(checksum))
    request.upload.onprogress = event => { if (event.lengthComputable) onProgress(event.loaded / event.total) }
    request.onload = () => request.status >= 200 && request.status < 300 ? resolve() : reject(new Error('Upload failed'))
    request.onerror = () => reject(new Error('Upload failed'))
    request.onabort = () => reject(new DOMException('Aborted', 'AbortError'))
    signal?.addEventListener('abort', () => request.abort(), { once: true })
    request.send(file)
  })
}
export const knowledgeKeys = {
  all: ['knowledge'] as const,
  workspace: (workspaceId: string) => [...knowledgeKeys.all, 'workspace', workspaceId] as const,
  contents: (folderId: string, options: { kind?: string, tagId?: string } = {}) => [...knowledgeKeys.all, 'contents', folderId, options] as const,
  document: (documentId: string) => [...knowledgeKeys.all, 'document', documentId] as const,
  versions: (documentId: string) => [...knowledgeKeys.all, 'versions', documentId] as const,
  ingestion: (documentId: string) => [...knowledgeKeys.all, 'ingestion', documentId] as const,
  fileVersions: (documentId: string) => [...knowledgeKeys.all, 'file-versions', documentId] as const,
  tags: (workspaceId: string) => [...knowledgeKeys.workspace(workspaceId), 'tags'] as const,
  trash: (workspaceId: string) => [...knowledgeKeys.workspace(workspaceId), 'trash'] as const,
}

export function useKnowledgeCapabilities(workspaceId: () => string | null) {
  return useQuery({ queryKey: computed(() => [...knowledgeKeys.all, 'capabilities', workspaceId()]), queryFn: ({ signal }) => knowledgeClient.capabilities(workspaceId()!, signal), enabled: computed(() => Boolean(workspaceId())) })
}

export function useFolderContents(folderId: () => string | null, options: () => { kind?: 'folder' | 'file' | 'note', tagId?: string | null } = () => ({})) {
  return useQuery({
    queryKey: computed(() => knowledgeKeys.contents(folderId()!, { kind: options().kind, tagId: options().tagId ?? undefined })),
    queryFn: ({ signal }) => knowledgeClient.contents(folderId()!, { kind: options().kind, tagId: options().tagId ?? undefined, signal }),
    enabled: computed(() => Boolean(folderId())),
  })
}

export function useKnowledgeDocument(documentId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.document(documentId()!)), queryFn: ({ signal }) => knowledgeClient.document(documentId()!, signal), enabled: computed(() => Boolean(documentId())) })
}

export function useKnowledgeVersions(documentId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.versions(documentId()!)), queryFn: ({ signal }) => knowledgeClient.versions(documentId()!, signal), enabled: computed(() => Boolean(documentId())) })
}

export function useFileVersions(documentId: () => string | null) {
  return useQuery({
    queryKey: computed(() => knowledgeKeys.fileVersions(documentId()!)),
    queryFn: ({ signal }) => knowledgeClient.fileVersions(documentId()!, signal),
    enabled: computed(() => Boolean(documentId())),
  })
}
export function useKnowledgeIngestion(documentId: () => string | null) {
  return useQuery({
    queryKey: computed(() => knowledgeKeys.ingestion(documentId()!)),
    queryFn: ({ signal }) => knowledgeClient.ingestion(documentId()!, signal),
    enabled: computed(() => Boolean(documentId())),
    refetchInterval: query => query.state.data?.jobs.some(job => ['queued', 'running', 'retryable', 'cancel_requested'].includes(job.status)) ? 1500 : false,
  })
}
export function useKnowledgeTrash(workspaceId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.trash(workspaceId()!)), queryFn: ({ signal }) => knowledgeClient.trash(workspaceId()!, { signal }), enabled: computed(() => Boolean(workspaceId())) })
}

export function useKnowledgeTags(workspaceId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.tags(workspaceId()!)), queryFn: ({ signal }) => knowledgeClient.tags(workspaceId()!, signal), enabled: computed(() => Boolean(workspaceId())) })
}

export function useKnowledgeMutations() {
  const client = useQueryClient()
  const invalidate = (documentId?: string, workspaceId?: string, folderId?: string) => {
    if (documentId) client.invalidateQueries({ queryKey: knowledgeKeys.document(documentId) })
    if (workspaceId) client.invalidateQueries({ queryKey: knowledgeKeys.workspace(workspaceId) })
    if (folderId) client.invalidateQueries({ queryKey: [...knowledgeKeys.all, 'contents', folderId] })
  }
  return {
    createFolder: useMutation({
      mutationFn: ({ workspaceId, name, parentId }: { workspaceId: string, name: string, parentId: string }) => knowledgeClient.createFolder(workspaceId, { name, parentId }),
      onSuccess: folder => invalidate(undefined, folder.workspaceId, folder.parentId ?? undefined),
    }),
    createNote: useMutation({
      mutationFn: ({ folderId, input }: { folderId: string, input: Parameters<typeof knowledgeClient.createNote>[1] }) => knowledgeClient.createNote(folderId, input),
      onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId),
    }),
    uploadFile: useMutation({
      mutationFn: async ({ folderId, file, title, onProgress, signal }: {
        folderId: string
        file: File
        title: string
        onProgress: (value: number) => void
        signal?: AbortSignal
      }) => {
        const checksum = await digestFile(file, signal)
        const ticket = await knowledgeClient.uploadTicket(folderId, {
          title,
          filename: file.name,
          mimeType: file.type,
          sizeBytes: file.size,
          checksum,
        })
        await putWithProgress(ticket.uploadUrl, file, ticket.requiredMimeType, checksum, onProgress, signal)
        return knowledgeClient.completeUpload(ticket.documentId, ticket.ticketId)
      },
      onSuccess: (_status, variables) => invalidate(undefined, undefined, variables.folderId),
    }),
    replaceFile: useMutation({
      mutationFn: async ({ document, file, onProgress, signal }: {
        document: { id: string, version: number, currentContentVersion?: number | null }
        file: File
        onProgress: (value: number) => void
        signal?: AbortSignal
      }) => {
        const checksum = await digestFile(file, signal)
        const ticket = await knowledgeClient.replacementUploadTicket(document.id, {
          title: file.name,
          filename: file.name,
          mimeType: file.type,
          sizeBytes: file.size,
          checksum,
          expectedVersion: document.version,
          expectedContentVersion: document.currentContentVersion ?? 1,
        })
        await putWithProgress(ticket.uploadUrl, file, ticket.requiredMimeType, checksum, onProgress, signal)
        return knowledgeClient.completeUpload(ticket.documentId, ticket.ticketId)
      },
      onSuccess: (_status, variables) => {
        invalidate(variables.document.id)
        client.invalidateQueries({ queryKey: knowledgeKeys.fileVersions(variables.document.id) })
        client.invalidateQueries({ queryKey: knowledgeKeys.ingestion(variables.document.id) })
      },
    }),

    retryIngestion: useMutation({ mutationFn: knowledgeClient.retryIngestion, onSuccess: status => invalidate(status.documentId) }),
    cancelIngestion: useMutation({ mutationFn: knowledgeClient.cancelIngestion, onSuccess: status => invalidate(status.documentId) }),
    updateDocument: useMutation({ mutationFn: ({ documentId, input }: { documentId: string, input: Parameters<typeof knowledgeClient.updateDocument>[1] }) => knowledgeClient.updateDocument(documentId, input), onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId) }),
    moveDocument: useMutation({ mutationFn: ({ documentId, folderId, expectedVersion }: { documentId: string, folderId: string, expectedVersion: number }) => knowledgeClient.moveDocument(documentId, folderId, expectedVersion), onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId) }),
    trashDocument: useMutation({ mutationFn: ({ documentId, expectedVersion }: { documentId: string, expectedVersion: number, folderId?: string }) => knowledgeClient.trashDocument(documentId, expectedVersion), onSuccess: (_value, variables) => { invalidate(variables.documentId); if (variables.folderId) client.invalidateQueries({ queryKey: [...knowledgeKeys.all, 'contents', variables.folderId] }) } }),
    deleteTag: useMutation({ mutationFn: ({ workspaceId, tagId, expectedVersion }: { workspaceId: string, tagId: string, expectedVersion: number }) => knowledgeClient.deleteTag(workspaceId, tagId, { expectedVersion }), onSuccess: (_value, variables) => client.invalidateQueries({ queryKey: knowledgeKeys.tags(variables.workspaceId) }) }),
    mergeTag: useMutation({ mutationFn: ({ workspaceId, tagId, targetTagId, expectedVersion, expectedTargetVersion }: { workspaceId: string, tagId: string, targetTagId: string, expectedVersion: number, expectedTargetVersion: number }) => knowledgeClient.mergeTag(workspaceId, tagId, { targetTagId, expectedVersion, expectedTargetVersion }), onSuccess: (_value, variables) => client.invalidateQueries({ queryKey: knowledgeKeys.tags(variables.workspaceId) }) }),
  }
}
