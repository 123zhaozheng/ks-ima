import type { Avatar } from './validators'

const unknownAvatar: Avatar = { type: 'icon', icon: 'sym_o_question_mark' }

export function kbAvatar(kb: { name: string, avatar?: Avatar | null } | null | undefined): Avatar {
  if (!kb) return unknownAvatar
  if (kb.avatar) return kb.avatar
  return { type: 'icon', icon: 'sym_o_deployed_code' }
}
