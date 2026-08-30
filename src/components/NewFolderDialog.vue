<template>
  <q-dialog
    v-model="show"
    @hide="name = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        {{ t('New folder') }}
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="name"
          outlined
          autofocus
          :label="t('Folder name')"
          data-testid="folder-name-input"
          @keyup.enter="create"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          :label="t('Cancel')"
        />
        <q-btn
          flat
          color="primary"
          :label="t('Create')"
          :loading="creating"
          :disable="!name.trim()"
          data-testid="folder-create-button"
          @click="create"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, ref } from 'vue'
import { Notify } from 'quasar'
import { useKnowledgeMutations } from 'src/composables/use-knowledge'
import { t } from 'src/utils/i18n'

type Folder = components['schemas']['Folder']

const props = defineProps<{
  modelValue: boolean
  workspaceId: string
  parentFolderId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  created: [Folder]
}>()

const show = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const name = ref('')
const creating = ref(false)
const mutations = useKnowledgeMutations()

async function create() {
  const folderName = name.value.trim()
  if (!folderName || creating.value) return
  creating.value = true
  try {
    const folder = await mutations.createFolder.mutateAsync({
      workspaceId: props.workspaceId,
      name: folderName,
      parentId: props.parentFolderId,
    })
    Notify.create({ type: 'positive', message: t('Folder created') })
    show.value = false
    emit('created', folder)
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Create failed') })
  } finally {
    creating.value = false
  }
}
</script>
