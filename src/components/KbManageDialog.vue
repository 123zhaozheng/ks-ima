<template>
  <q-dialog
    v-model="show"
    data-testid="kb-manage-dialog"
  >
    <q-card class="kb-manage-card">
      <q-card-section
        flex
        items-center
      >
        <div class="kb-manage-title">
          {{ t('Manage knowledge base') }}
        </div>
        <q-space />
        <q-btn
          v-close-popup
          flat
          dense
          round
          icon="sym_o_close"
          :title="t('Close')"
        />
      </q-card-section>
      <q-separator />
      <q-card-section class="kb-manage-body">
        <div
          v-if="isOwner"
          class="kb-manage-section"
        >
          <div class="kb-manage-section-title">
            {{ t('Rename knowledge base') }}
          </div>
          <div class="kb-rename-row">
            <q-input
              v-model="name"
              dense
              outlined
              :label="t('Knowledge base name')"
              data-testid="kb-rename-input"
              @keyup.enter="rename"
            />
            <q-btn
              dense
              no-caps
              unelevated
              color="primary"
              :label="t('Rename')"
              :loading="renaming"
              :disable="!canRename"
              data-testid="kb-rename-save"
              @click="rename"
            />
          </div>
        </div>
        <kb-members-panel
          :kb-id="kb.id"
          :is-owner="isOwner"
          @left="show = false"
        />
        <kb-share-links-panel
          v-if="isOwner"
          :kb-id="kb.id"
        />
        <div
          v-if="isOwner"
          class="kb-manage-section"
        >
          <div class="kb-manage-section-title kb-manage-danger-title">
            {{ t('Danger zone') }}
          </div>
          <div class="kb-danger-row">
            <q-btn
              v-if="!archived"
              flat
              dense
              no-caps
              icon="sym_o_archive"
              :label="t('Archive knowledge base')"
              data-testid="kb-archive"
              @click="confirmArchive"
            />
            <q-btn
              v-else
              flat
              dense
              no-caps
              icon="sym_o_unarchive"
              :label="t('Restore knowledge base')"
              data-testid="kb-restore"
              @click="restore"
            />
            <q-btn
              v-if="archived"
              flat
              dense
              no-caps
              icon="sym_o_delete_forever"
              color="negative"
              :label="t('Delete knowledge base')"
              data-testid="kb-delete"
              @click="confirmDeleteKb"
            />
          </div>
          <div class="tk-caption">
            {{ archived
              ? t('Only archived knowledge bases can be deleted.')
              : t('Archive the knowledge base before deleting it.') }}
          </div>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import KbMembersPanel from 'src/components/KbMembersPanel.vue'
import KbShareLinksPanel from 'src/components/KbShareLinksPanel.vue'
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient } from 'src/utils/identity-client'
import type { KnowledgeBaseSummary } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  modelValue: boolean
  kb: KnowledgeBaseSummary
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
}>()

const show = computed({
  get: () => props.modelValue,
  set: value => emit('update:modelValue', value),
})

const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()

const isOwner = computed(() => props.kb.role === 'owner')
const archived = computed(() => Boolean(props.kb.archivedAt))

const name = ref(props.kb.name)
const renaming = ref(false)
const canRename = computed(() => name.value.trim().length > 0 && name.value.trim() !== props.kb.name)

watch(show, open => {
  if (open) name.value = props.kb.name
})

function invalidateKb() {
  queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
  queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member', props.kb.id] })
}

async function rename() {
  const next = name.value.trim()
  if (!next || renaming.value || next === props.kb.name) return
  renaming.value = true
  try {
    const result = await identityClient.renameKnowledgeBase(props.kb.id, { name: next })
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Rename failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Renamed') })
    invalidateKb()
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Rename failed') })
  } finally {
    renaming.value = false
  }
}

function confirmArchive() {
  $q.dialog({
    title: t('Archive knowledge base'),
    message: t('Are you sure you want to archive "{0}"? Members will no longer be able to add or change content.', props.kb.name),
    cancel: true,
    ok: {
      label: t('Archive'),
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.archiveKnowledgeBase(props.kb.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Archive failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Knowledge base archived') })
    invalidateKb()
  })
}

async function restore() {
  const result = await identityClient.restoreKnowledgeBase(props.kb.id)
  if (result.error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Restore failed') })
    return
  }
  Notify.create({ type: 'positive', message: t('Knowledge base restored') })
  invalidateKb()
}

function confirmDeleteKb() {
  $q.dialog({
    title: t('Delete knowledge base'),
    message: t('Are you sure you want to delete "{0}"? This cannot be undone.', props.kb.name),
    cancel: true,
    ok: {
      label: t('Delete'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.deleteKnowledgeBase(props.kb.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Delete failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Knowledge base deleted') })
    show.value = false
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    // The store falls back to the next knowledge base once this one is gone.
    kbStore.id = null
  })
}
</script>

<style scoped>
.kb-manage-card {
  width: min(92vw, 520px);
  border-radius: var(--tk-radius-lg);
}

.kb-manage-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--tk-text);
}

.kb-manage-body {
  max-height: 70vh;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-5);
}

.kb-rename-row {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-2);
}

.kb-rename-row .q-input {
  flex: 1;
}

.kb-danger-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-2);
  margin-bottom: var(--tk-space-1);
}

.kb-manage-danger-title {
  color: var(--tk-danger);
}
</style>

<style>
/* Shared section scaffolding for the manage dialog panels. Flat selectors only — Chrome 109 policy. */
.kb-manage-section {
  display: flex;
  flex-direction: column;
}

.kb-manage-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--tk-text-secondary);
}

.kb-manage-loading,
.kb-manage-empty {
  padding: var(--tk-space-3);
  font-size: 13px;
  color: var(--tk-text-tertiary);
  text-align: center;
}

.kb-manage-footer {
  margin-top: var(--tk-space-2);
  padding-top: var(--tk-space-2);
  border-top: 1px solid var(--tk-border);
}
</style>
