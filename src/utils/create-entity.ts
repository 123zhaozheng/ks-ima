import type { EntityType } from 'app/src-shared/utils/validators'
import { mutate, z } from 'src/utils/zero-session'
import { genId } from 'app/src-shared/utils/id'
import { mutators } from 'app/src-shared/mutators'
import { queries } from 'app/src-shared/queries'
import router from 'src/router'
import { Dialog } from 'quasar'
import { t } from './i18n'
import { providerTypes } from './values'
import CreateShortcutDialog from 'src/components/CreateShortcutDialog.vue'
import { openCreatedEntity } from './open-created-entity'

export async function createEntity(parentId: string, type: EntityType, signal?: AbortSignal) {
  if (type === 'chat') {
    const id = genId()
    const mutation = mutate(mutators.createChat({
      ids: [id, genId()],
      parentId,
    }))
    await mutation.client
    const serverResult = await mutation.server
    if (serverResult.type === 'error') throw new Error(serverResult.error.message)
    const opened = await openCreatedEntity(
      () => z.run(queries.fullChat(id), { type: 'complete' }),
      () => router.push(`/chat/${id}`),
      { signal },
    )
    if (!opened) throw new Error(t('Created chat is not available. Please try again.'))
  } else if (type === 'provider') {
    const defaultType = 'openaiCompatible'
    const id = genId()
    const { label, avatar, initialSettings = {} } = providerTypes[defaultType]
    await mutate(mutators.createProvider({
      id,
      parentId,
      name: label,
      avatar,
      type: defaultType,
      settings: initialSettings,
    })).client
    router.push(`/provider/${id}`)
  } else if (type === 'shortcut') {
    Dialog.create({
      component: CreateShortcutDialog,
      componentProps: {
        parentId,
      },
    })
  } else if (type === 'folder') {
    Dialog.create({
      title: t('Create Folder'),
      prompt: {
        model: '',
        label: t('Name'),
      },
      cancel: true,
      ok: t('Create'),
    }).onOk(name => {
      mutate(mutators.createFolder({
        id: genId(),
        name,
        parentId,
      }))
    })
  }
}
