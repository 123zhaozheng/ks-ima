import type { Avatar } from 'app/src-shared/utils/validators'
import type { Row } from '@rocicorp/zero'
import { t } from './i18n'
import { typeAvatar } from 'app/src-shared/utils/functions'
import { stringHue } from './functions'

const unknownAvatar: Avatar = { type: 'icon', icon: 'sym_o_question_mark' }

export type PartialEntity = Pick<Row['entity'], 'avatar' | 'type' | 'id' | 'name'>

export function entityAvatar(entity: PartialEntity | null | undefined): Avatar {
  if (!entity) return unknownAvatar
  if (entity.avatar) return entity.avatar
  if (entity.type === 'assistant') return { type: 'text', text: 'AI', hue: stringHue(entity.id) }
  return typeAvatar(entity.type) ?? unknownAvatar
}

export function entityName(entity: PartialEntity | null | undefined) {
  if (!entity) return ''
  if (entity.name === '/') return t('All files')
  if (entity.name === '$chat') return t('Chat')
  if (entity.name === '$search') return t('Search')
  if (entity.name === '$pages') return t('Notes')
  if (entity.name === '$files') return t('Files')
  if (entity.name === '$assistants') return t('Assistants')
  if (entity.name === '$providers') return t('Providers')
  if (entity.name === '$shortcuts') return t('Shortcuts')
  if (entity.name === '$defaultAssistant') return t('Default Assistant')

  if (entity.name) return entity.name
  if (entity.type === 'folder') return t('New folder')
  if (entity.type === 'search') return t('New search')
  if (entity.type === 'chat') return t('New chat')
  if (entity.type === 'page') return t('New note')
  if (entity.type === 'provider') return t('New provider')
  if (entity.type === 'assistant') return t('New assistant')
  if (entity.type === 'item') return t('New item')
  return ''
}

export function userAvatar(user: Row['user'] | null | undefined): Avatar {
  if (!user) return unknownAvatar
  if (user.image) return { type: 'url', url: user.image, hue: stringHue(user.id) }
  return { type: 'text', text: user.name[0].toUpperCase(), hue: stringHue(user.id) }
}

export function workspaceAvatar(workspace: Row['workspace'] | null | undefined): Avatar {
  if (!workspace) return unknownAvatar
  if (workspace.avatar) return workspace.avatar
  return { type: 'icon', icon: 'sym_o_deployed_code' }
}
