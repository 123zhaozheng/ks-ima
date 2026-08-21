import { mutate } from 'src/utils/zero-session'
import { genId, genIds } from 'app/src-shared/utils/id'
import { mutators } from 'app/src-shared/mutators'
import { client } from 'src/utils/hc'
import { useWorkspaceStore } from 'src/stores/workspace'

function toResults(hits: { name?: string, content?: string | null }[] | unknown, q: string) {
  return (Array.isArray(hits) ? hits : []).map(h => ({
    title: (h as any).name || q,
    url: 'https://intranet.local/kb',
    content: (h as any).content || '',
  }))
}

export async function createSearch(q: string, parentId: string) {
  const workspaceStore = useWorkspaceStore()
  const resp = await client.api.search.$post({
    json: { workspaceId: workspaceStore.id!, q, types: ['page', 'item', 'chat'], limit: 20 },
  })
  const hits = await resp.json()
  const id = genId()
  await mutate(mutators.createSearch({
    ids: [id, ...genIds(3)],
    parentId,
    q,
    results: toResults(hits, q),
  })).client
  return id
}

export async function createSearchRecord(entityId: string, q: string) {
  const workspaceStore = useWorkspaceStore()
  const resp = await client.api.search.$post({
    json: { workspaceId: workspaceStore.id!, q, types: ['page', 'item', 'chat'], limit: 20 },
  })
  const hits = await resp.json()
  const id = genId()
  const aId = genId()
  await mutate(mutators.createSearchRecord({
    ids: [id, aId, genId()],
    entityId,
    q,
    results: toResults(hits, q),
  })).client
  return id
}
