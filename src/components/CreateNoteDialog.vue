<template>
  <q-dialog
    v-model="show"
    @hide="title = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        {{ t('New note') }}
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="title"
          outlined
          autofocus
          :label="t('Title')"
          data-testid="note-title-input"
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
          :disable="!title.trim()"
          data-testid="note-create-button"
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

type Document = components['schemas']['DocumentResponse']

const props = defineProps<{
  modelValue: boolean
  folderId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  created: [Document]
}>()

const show = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const title = ref('')
const creating = ref(false)
const mutations = useKnowledgeMutations()

async function create() {
  const name = title.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    const document = await mutations.createNote.mutateAsync({
      folderId: props.folderId,
      input: { title: name, markdown: '' },
    })
    Notify.create({ type: 'positive', message: t('Note created') })
    show.value = false
    emit('created', document)
  } catch (error) {
    Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Create failed') })
  } finally {
    creating.value = false
  }
}
</script>
