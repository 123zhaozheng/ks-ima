import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { knowledgeClient } from 'src/api/knowledge-client'
import { computed } from 'vue'

export const knowledgeKeys = {
  all: ['knowledge'] as const,
  workspace: (workspaceId: string) => [...knowledgeKeys.all, 'workspace', workspaceId] as const,
  contents: (folderId: string, options: { kind?: string, tagId?: string } = {}) => [...knowledgeKeys.all, 'contents', folderId, options] as const,
  document: (documentId: string) => [...knowledgeKeys.all, 'document', documentId] as const,
  versions: (documentId: string) => [...knowledgeKeys.all, 'versions', documentId] as const,
  tags: (workspaceId: string) => [...knowledgeKeys.workspace(workspaceId), 'tags'] as const,
  trash: (workspaceId: string) => [...knowledgeKeys.workspace(workspaceId), 'trash'] as const,
}

export function useKnowledgeCapabilities(workspaceId: () => string | null) {
  return useQuery({ queryKey: computed(() => [...knowledgeKeys.all, 'capabilities', workspaceId()]), queryFn: ({ signal }) => knowledgeClient.capabilities(workspaceId()!, signal), enabled: computed(() => Boolean(workspaceId())) })
}

export function useFolderContents(folderId: () => string | null, options: { kind?: 'folder' | 'file' | 'note', tagId?: string } = {}) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.contents(folderId()!, options)), queryFn: ({ signal }) => knowledgeClient.contents(folderId()!, { ...options, signal }), enabled: computed(() => Boolean(folderId())) })
}

export function useKnowledgeDocument(documentId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.document(documentId()!)), queryFn: ({ signal }) => knowledgeClient.document(documentId()!, signal), enabled: computed(() => Boolean(documentId())) })
}

export function useKnowledgeVersions(documentId: () => string | null) {
  return useQuery({ queryKey: computed(() => knowledgeKeys.versions(documentId()!)), queryFn: ({ signal }) => knowledgeClient.versions(documentId()!, signal), enabled: computed(() => Boolean(documentId())) })
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
    createNote: useMutation({ mutationFn: ({ folderId, input }: { folderId: string, input: Parameters<typeof knowledgeClient.createNote>[1] }) => knowledgeClient.createNote(folderId, input), onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId) }),
    updateDocument: useMutation({ mutationFn: ({ documentId, input }: { documentId: string, input: Parameters<typeof knowledgeClient.updateDocument>[1] }) => knowledgeClient.updateDocument(documentId, input), onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId) }),
    moveDocument: useMutation({ mutationFn: ({ documentId, folderId, expectedVersion }: { documentId: string, folderId: string, expectedVersion: number }) => knowledgeClient.moveDocument(documentId, folderId, expectedVersion), onSuccess: document => invalidate(document.id, document.workspaceId, document.folderId) }),
    trashDocument: useMutation({ mutationFn: ({ documentId, expectedVersion }: { documentId: string, expectedVersion: number }) => knowledgeClient.trashDocument(documentId, expectedVersion), onSuccess: (_value, variables) => invalidate(variables.documentId) }),
    deleteTag: useMutation({ mutationFn: ({ workspaceId, tagId, expectedVersion }: { workspaceId: string, tagId: string, expectedVersion: number }) => knowledgeClient.deleteTag(workspaceId, tagId, { expectedVersion }), onSuccess: (_value, variables) => client.invalidateQueries({ queryKey: knowledgeKeys.tags(variables.workspaceId) }) }),
    mergeTag: useMutation({ mutationFn: ({ workspaceId, tagId, targetTagId, expectedVersion, expectedTargetVersion }: { workspaceId: string, tagId: string, targetTagId: string, expectedVersion: number, expectedTargetVersion: number }) => knowledgeClient.mergeTag(workspaceId, tagId, { targetTagId, expectedVersion, expectedTargetVersion }), onSuccess: (_value, variables) => client.invalidateQueries({ queryKey: knowledgeKeys.tags(variables.workspaceId) }) }),
  }
}
