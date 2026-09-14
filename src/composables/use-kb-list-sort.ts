import type { KbListGroup, KbListSort } from 'src/api/knowledge-client'
import { localReactive } from './local-reactive'

// User's folder-list sort preference, persisted across folders and sessions.
// manual + folders_first reproduces the historical default ordering.
export function useKbListSort() {
  return localReactive<{ sort: KbListSort, group: KbListGroup }>('kb-list-sort', {
    sort: 'manual',
    group: 'folders_first',
  })
}
