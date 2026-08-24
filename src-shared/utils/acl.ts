import type { WorkspaceRole } from './validators'

export const ACL_ACTIONS = ['view', 'ask', 'edit', 'delete', 'manage'] as const
export type AclAction = typeof ACL_ACTIONS[number]

export type Ace = {
  principalType: 'role' | 'user'
  principalId: string
  actions: AclAction[]
}

export type FolderAcl = {
  inherit: boolean
  aces: Ace[]
}

export const ROLE_DEFAULT_ACTIONS: Record<WorkspaceRole, AclAction[]> = {
  guest: ['view', 'ask'],
  member: ['view', 'ask', 'edit', 'delete'],
  admin: ['view', 'ask', 'edit', 'delete', 'manage'],
  owner: ['view', 'ask', 'edit', 'delete', 'manage'],
}

export function parseFolderAcl(conf: Record<string, any> | null | undefined): FolderAcl | null {
  const acl = conf?.acl
  if (!acl || typeof acl !== 'object') return null
  const validActions = new Set<AclAction>(ACL_ACTIONS)
  return {
    inherit: acl.inherit !== false,
    aces: Array.isArray(acl.aces)
      ? acl.aces.flatMap((ace: unknown) => {
        if (!ace || typeof ace !== 'object') return []
        const value = ace as Record<string, unknown>
        if (value.principalType !== 'role' && value.principalType !== 'user') return []
        if (typeof value.principalId !== 'string' || !value.principalId) return []
        const actions = Array.isArray(value.actions)
          ? value.actions.filter((action): action is AclAction => validActions.has(action as AclAction))
          : []
        return [{
          principalType: value.principalType,
          principalId: value.principalId,
          actions,
        }]
      })
      : [],
  }
}

export function personalAcl(userId: string): FolderAcl {
  return {
    inherit: false,
    aces: [{
      principalType: 'user',
      principalId: userId,
      actions: [...ACL_ACTIONS],
    }],
  }
}

/** ancestorConfs: from the entity itself up to workspace root (inclusive). */
export function resolveActions(
  role: WorkspaceRole,
  userId: string,
  ancestorConfs: Array<Record<string, any> | null | undefined>,
): Set<AclAction> {
  if (role === 'owner') return new Set(ACL_ACTIONS)

  let breakAcl: FolderAcl | null = null
  for (const conf of ancestorConfs) {
    const acl = parseFolderAcl(conf)
    if (acl && !acl.inherit) {
      breakAcl = acl
      break
    }
  }

  const actions = new Set<AclAction>()
  if (!breakAcl) {
    ROLE_DEFAULT_ACTIONS[role].forEach(a => actions.add(a))
    return actions
  }

  for (const ace of breakAcl.aces) {
    if (ace.principalType === 'role' && ace.principalId === role) {
      ace.actions.forEach(a => actions.add(a))
    }
    if (ace.principalType === 'user' && ace.principalId === userId) {
      ace.actions.forEach(a => actions.add(a))
    }
  }
  return actions
}

export function canAction(
  role: WorkspaceRole | undefined,
  userId: string | undefined,
  ancestorConfs: Array<Record<string, any> | null | undefined>,
  action: AclAction,
) {
  if (!role || !userId) return false
  const actions = resolveActions(role, userId, ancestorConfs)
  // Asking can reveal source text through both the answer and its citations.
  return actions.has(action) && (action !== 'ask' || actions.has('view'))
}
