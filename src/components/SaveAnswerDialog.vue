<template>
  <q-dialog
    :model-value="modelValue"
    data-testid="save-as-note-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <q-card class="save-answer-dialog">
      <q-card-section class="save-answer-title">
        {{ t('Save answer as note') }}
      </q-card-section>
      <q-card-section class="save-answer-field">
        <q-input
          v-model="title"
          outlined
          dense
          :label="t('Title')"
          data-testid="save-as-note-title"
        />
      </q-card-section>
      <q-card-section class="save-answer-folder">
        <div class="save-answer-folder-label">
          {{ t('Choose a folder') }}
        </div>
        <folder-picker-list
          :workspace-id="workspaceId"
          :selected-id="folder?.id ?? null"
          @select="folder = $event"
        />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          :label="t('Cancel')"
          @click="emit('update:modelValue', false)"
        />
        <q-btn
          color="primary"
          :label="t('Save')"
          :loading="createNote.isPending.value"
          :disable="folder === undefined"
          data-testid="save-as-note-confirm"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { ref, watch } from 'vue'
import { Notify } from 'quasar'
import FolderPickerList from 'src/components/FolderPickerList.vue'
import type { PickedFolder } from 'src/components/folder-picker-list'
import { useKnowledgeMutations } from 'src/composables/use-knowledge'
import { apiErrorMessage } from 'src/utils/api-error'
import { t } from 'src/utils/i18n'

type Citation = components['schemas']['CitationResponse'] & { title?: string }

const props = defineProps<{
  modelValue: boolean
  answer: string
  citations: Citation[]
  workspaceId: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: [documentId: string]
}>()

const createNote = useKnowledgeMutations().createNote
const title = ref('')
// undefined = nothing picked yet; null = "Whole workspace" (root folder).
const folder = ref<PickedFolder | null | undefined>(undefined)

// Default the note title to the first line of the answer.
watch(() => props.modelValue, open => {
  if (!open) return
  folder.value = undefined
  const firstLine = props.answer.split('\n').map(line => line.trim()).find(Boolean) ?? ''
  title.value = firstLine.replace(/^#+\s*/, '').slice(0, 200) || t('Saved answer')
})

function noteMarkdown(): string {
  if (props.citations.length === 0) return props.answer
  const appendix = props.citations
    .map(citation => `1. "${citation.quote.trim()}"${citation.title ? ` — ${citation.title}` : ''}`)
    .join('\n')
  return `${props.answer}\n\n---\n\n## ${t('Sources')}\n\n${appendix}`
}

async function save() {
  if (folder.value === undefined) return
  try {
    const document = await createNote.mutateAsync({
      folderId: folder.value?.id ?? props.workspaceId,
      input: { title: title.value.trim() || t('Saved answer'), markdown: noteMarkdown() },
    })
    Notify.create({ type: 'positive', message: t('Note saved') })
    emit('created', document.id)
    emit('update:modelValue', false)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Save failed') })
  }
}
</script>

<style scoped>
.save-answer-dialog {
  min-width: 320px;
  max-width: 420px;
  border-radius: var(--tk-radius-lg);
}

.save-answer-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--tk-text);
}

.save-answer-folder {
  padding-top: 0;
}

.save-answer-folder-label {
  font-size: 13px;
  color: var(--tk-text-secondary);
  margin-bottom: var(--tk-space-1);
}
</style>
