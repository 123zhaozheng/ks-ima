import type { Avatar } from './validators'

const unknownAvatar: Avatar = { type: 'icon', icon: 'sym_o_question_mark' }

export function workspaceAvatar(workspace: { name: string, avatar?: Avatar | null } | null | undefined): Avatar {
  if (!workspace) return unknownAvatar
  if (workspace.avatar) return workspace.avatar
  return { type: 'icon', icon: 'sym_o_deployed_code' }
}
