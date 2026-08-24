<template>
  <div
    flex
    gap-1
  >
    <q-btn
      flat
      no-caps
      grow
      align="left"
      icon="sym_o_create_new_folder"
      :label="t('New folder')"
      bg-pri-c
      text-on-pri-c
      @click="createEntity(rightDirStore.dirId!, 'folder')"
    />
    <q-btn
      flat
      icon="sym_o_add"
    >
      <q-menu>
        <q-list>
          <menu-item
            :label="t('New folder')"
            icon="sym_o_create_new_folder"
            @click="createEntity(rightDirStore.dirId!, 'folder')"
          />
          <menu-item
            :label="t('Upload files')"
            icon="sym_o_upload_file"
            @click="selectFile(files => rightDirStore.dirId && uploadKnowledge(rightDirStore.dirId, files.map(file => ({ file, relativePath: file.name }))), { multiple: true })"
          />
          <menu-item
            :label="t('Upload folder')"
            icon="sym_o_drive_folder_upload"
            @click="rightDirStore.dirId && selectFolder(files => uploadKnowledge(rightDirStore.dirId!, files))"
          />
          <q-separator />
          <menu-item
            :label="t('Ask')"
            icon="sym_o_chat"
            @click="askKnowledge"
          />
        </q-list>
      </q-menu>
    </q-btn>
  </div>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useRightDirStore } from 'src/stores/right-dir'
import MenuItem from './MenuItem.vue'
import { createEntity } from 'src/utils/create-entity'
import { selectFile } from 'src/utils/select-file'
import { selectFolder, uploadKnowledge } from 'src/utils/knowledge-upload'
import { useAskKnowledge } from 'src/composables/ask-knowledge'

const rightDirStore = useRightDirStore()
const askKnowledge = useAskKnowledge()
</script>
