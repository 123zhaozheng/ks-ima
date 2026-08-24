export const KNOWLEDGE_TYPES = new Set(['folder', 'item'])

export const SYSTEM_ENTITY_NAMES = new Set([
  '$trash',
  '$search',
  '$chat',
  '$providers',
  '$pages',
  '$translations',
  '$channels',
  '$files',
  '$assistants',
  '$mcpPlugins',
  '$shortcuts',
  '$defaultAssistant',
])

export function isKnowledgeEntity(entity: { type: string, name?: string | null }) {
  return KNOWLEDGE_TYPES.has(entity.type) && !SYSTEM_ENTITY_NAMES.has(entity.name ?? '')
}

export function systemFolderId(
  entities: { id: string, name?: string | null, rootId?: string | null }[],
  workspaceId: string,
  name: string,
) {
  return entities.find(e => e.name === name && e.rootId === workspaceId)?.id ?? workspaceId
}

export function chatParentId(
  shortcuts: { type?: string | null, dirId?: string | null }[],
  entities: { id: string, name?: string | null, rootId?: string | null }[],
  workspaceId: string,
) {
  const shortcut = shortcuts.find(s => s.type === 'chat')
  if (shortcut?.dirId) return shortcut.dirId
  const folder = entities.find(e => e.name === '$chat' && e.rootId === workspaceId)
  return folder?.id ?? workspaceId
}

export type ParseStatus = 'parsing' | 'ready' | 'unparsed' | 'failed'

export function itemParseStatus(
  item?: { text?: string | null, blobId?: string | null } | null,
  conf?: Record<string, any> | null,
): ParseStatus {
  const status = conf?.parseStatus
  if (status === 'failed') return 'failed'
  if (status === 'queued' || status === 'parsing') return 'parsing'
  if (status === 'ready') return 'ready'
  if (status === 'unparsed') return 'unparsed'
  if (!item) return 'parsing'
  if (item.text?.trim()) return 'ready'
  if (item.blobId) return 'unparsed'
  return 'parsing'
}
