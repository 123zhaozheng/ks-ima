import type { components } from 'src/api/generated/schema'
import { imaClient } from './ima-client'

type ContentPage = components['schemas']['ContentPage']
type Document = components['schemas']['DocumentResponse']
type Folder = components['schemas']['Folder']
type FolderCreate = components['schemas']['FolderCreateRequest']
type Capabilities = components['schemas']['KnowledgeCapabilities']
type NoteInput = components['schemas']['NoteCreateRequest']
type DocumentPatch = components['schemas']['DocumentPatchRequest']
type Version = components['schemas']['VersionResponse']
type Tag = components['schemas']['TagResponse']
type TagCreate = components['schemas']['TagCreateRequest']
type TagPatch = components['schemas']['TagPatchRequest']
type TagDelete = components['schemas']['TagDeleteRequest']
type TagMerge = components['schemas']['TagMergeRequest']
type TrashPage = components['schemas']['TrashPage']
type UploadTicket = components['schemas']['UploadTicketResponse']
type UploadTicketInput = components['schemas']['UploadTicketRequest']
type IngestionStatus = components['schemas']['IngestionStatusResponse']
type FileAccess = components['schemas']['FileAccessResponse']
type FileVersions = components['schemas']['FileVersionPage']
type ReplaceFileInput = components['schemas']['ReplaceFileRequest']

const path = (value: string) => encodeURIComponent(value)

export const knowledgeClient = {
  capabilities: (workspaceId: string, signal?: AbortSignal) => imaClient.request<Capabilities>(`/api/v1/workspaces/${path(workspaceId)}/knowledge-capabilities`, { signal }),
  createFolder: (workspaceId: string, input: FolderCreate) => imaClient.request<Folder>(`/api/v1/workspaces/${path(workspaceId)}/folders`, { method: 'POST', body: JSON.stringify(input) }),
  uploadTicket: (folderId: string, input: UploadTicketInput) => imaClient.request<UploadTicket>(`/api/v1/folders/${path(folderId)}/files/upload-ticket`, { method: 'POST', body: JSON.stringify(input) }),
  replacementUploadTicket: (documentId: string, input: ReplaceFileInput) => imaClient.request<UploadTicket>(`/api/v1/documents/${path(documentId)}/file-versions/upload-ticket`, { method: 'POST', body: JSON.stringify(input) }),
  fileVersions: (documentId: string, signal?: AbortSignal) => imaClient.request<FileVersions>(`/api/v1/documents/${path(documentId)}/file-versions`, { signal }),
  completeUpload: (documentId: string, ticketId: string) => imaClient.request<IngestionStatus>(`/api/v1/documents/${path(documentId)}/file-versions/complete`, { method: 'POST', body: JSON.stringify({ ticketId }) }),
  ingestion: (documentId: string, signal?: AbortSignal) => imaClient.request<IngestionStatus>(`/api/v1/documents/${path(documentId)}/ingestion`, { signal }),
  retryIngestion: (documentId: string) => imaClient.request<IngestionStatus>(`/api/v1/documents/${path(documentId)}/ingestion/retry`, { method: 'POST' }),
  cancelIngestion: (documentId: string) => imaClient.request<IngestionStatus>(`/api/v1/documents/${path(documentId)}/ingestion/cancel`, { method: 'POST' }),
  download: (documentId: string, signal?: AbortSignal) => imaClient.request<FileAccess>(`/api/v1/documents/${path(documentId)}/file/download`, { signal }),
  preview: (documentId: string, signal?: AbortSignal) => imaClient.request<FileAccess>(`/api/v1/documents/${path(documentId)}/file/preview`, { signal }),
  contents: (folderId: string, options: { cursor?: string, limit?: number, kind?: 'folder' | 'file' | 'note', tagId?: string, signal?: AbortSignal } = {}) => {
    const params = new URLSearchParams()
    if (options.cursor) params.set('cursor', options.cursor)
    if (options.limit) params.set('limit', String(options.limit))
    if (options.kind) params.set('kind', options.kind)
    if (options.tagId) params.set('tagId', options.tagId)
    return imaClient.request<ContentPage>(`/api/v1/folders/${path(folderId)}/contents?${params}`, { signal: options.signal })
  },
  document: (documentId: string, signal?: AbortSignal) => imaClient.request<Document>(`/api/v1/documents/${path(documentId)}`, { signal }),
  createNote: (folderId: string, input: NoteInput) => imaClient.request<Document>(`/api/v1/folders/${path(folderId)}/notes`, { method: 'POST', body: JSON.stringify(input) }),
  updateDocument: (documentId: string, input: DocumentPatch) => imaClient.request<Document>(`/api/v1/documents/${path(documentId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveDocument: (documentId: string, folderId: string, expectedVersion: number) => imaClient.request<Document>(`/api/v1/documents/${path(documentId)}/move`, { method: 'POST', body: JSON.stringify({ folderId, expectedVersion }) }),
  trashDocument: (documentId: string, expectedVersion: number) => imaClient.request<void>(`/api/v1/documents/${path(documentId)}/trash`, { method: 'POST', body: JSON.stringify({ expectedVersion }) }),
  restoreDocument: (documentId: string, expectedVersion: number, destinationFolderId?: string) => imaClient.request<void>(`/api/v1/documents/${path(documentId)}/restore`, { method: 'POST', body: JSON.stringify({ expectedVersion, destinationFolderId }) }),
  deleteDocument: (documentId: string) => imaClient.request<void>(`/api/v1/documents/${path(documentId)}`, { method: 'DELETE' }),
  versions: (documentId: string, signal?: AbortSignal) => imaClient.request<Version[]>(`/api/v1/documents/${path(documentId)}/versions`, { signal }),
  restoreVersion: (documentId: string, version: number, expectedVersion: number) => imaClient.request<Document>(`/api/v1/documents/${path(documentId)}/versions/${version}/restore`, { method: 'POST', body: JSON.stringify({ expectedVersion }) }),
  tags: (workspaceId: string, signal?: AbortSignal) => imaClient.request<Tag[]>(`/api/v1/workspaces/${path(workspaceId)}/tags`, { signal }),
  createTag: (workspaceId: string, input: TagCreate) => imaClient.request<Tag>(`/api/v1/workspaces/${path(workspaceId)}/tags`, { method: 'POST', body: JSON.stringify(input) }),
  updateTag: (workspaceId: string, tagId: string, input: TagPatch) => imaClient.request<Tag>(`/api/v1/workspaces/${path(workspaceId)}/tags/${path(tagId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteTag: (workspaceId: string, tagId: string, input: TagDelete) => imaClient.request<void>(`/api/v1/workspaces/${path(workspaceId)}/tags/${path(tagId)}`, { method: 'DELETE', body: JSON.stringify(input) }),
  mergeTag: (workspaceId: string, tagId: string, input: TagMerge) => imaClient.request<void>(`/api/v1/workspaces/${path(workspaceId)}/tags/${path(tagId)}/merge`, { method: 'POST', body: JSON.stringify(input) }),
  replaceTags: (documentId: string, tagIds: string[]) => imaClient.request<void>(`/api/v1/documents/${path(documentId)}/tags`, { method: 'PUT', body: JSON.stringify({ tagIds }) }),
  trash: (workspaceId: string, options: { cursor?: string, limit?: number, signal?: AbortSignal } = {}) => {
    const params = new URLSearchParams()
    if (options.cursor) params.set('cursor', options.cursor)
    if (options.limit) params.set('limit', String(options.limit))
    return imaClient.request<TrashPage>(`/api/v1/workspaces/${path(workspaceId)}/trash?${params}`, { signal: options.signal })
  },
}
