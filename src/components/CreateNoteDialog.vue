<template>
  <q-dialog
    v-model="show"
    @hide="title = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        新建笔记
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="title"
          outlined
          autofocus
          label="标题"
          data-testid="note-title-input"
          @keyup.enter="create"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          v-close-popup
          flat
          label="取消"
        />
        <q-btn
          flat
          color="primary"
          label="创建"
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
import { apiErrorMessage } from 'src/utils/api-error'

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
    Notify.create({ type: 'positive', message: '笔记已创建' })
    show.value = false
    emit('created', document)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
  } finally {
    creating.value = false
  }
}
</script>
