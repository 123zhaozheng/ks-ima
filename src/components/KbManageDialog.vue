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
          管理知识库
        </div>
        <q-space />
        <q-btn
          v-close-popup
          flat
          dense
          round
          icon="sym_o_close"
          title="关闭"
        />
      </q-card-section>
      <q-separator />
      <q-card-section class="kb-manage-body">
        <div
          v-if="isOwner"
          class="kb-manage-section"
        >
          <div class="kb-manage-section-title">
            重命名知识库
          </div>
          <div class="kb-rename-row">
            <q-input
              v-model="name"
              dense
              outlined
              label="知识库名称"
              data-testid="kb-rename-input"
              @keyup.enter="rename"
            />
            <q-btn
              dense
              no-caps
              unelevated
              color="primary"
              label="重命名"
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
        <div
          v-if="isOwner"
          ref="shareAnchor"
        >
          <kb-share-links-panel :kb-id="kb.id" />
        </div>
        <div
          v-if="isOwner"
          class="kb-manage-section"
        >
          <div class="kb-manage-section-title kb-manage-danger-title">
            危险区
          </div>
          <div class="kb-danger-row">
            <q-btn
              v-if="!archived"
              flat
              dense
              no-caps
              icon="sym_o_archive"
              label="归档知识库"
              data-testid="kb-archive"
              @click="confirmArchive"
            />
            <q-btn
              v-else
              flat
              dense
              no-caps
              icon="sym_o_unarchive"
              label="恢复知识库"
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
              label="删除知识库"
              data-testid="kb-delete"
              @click="confirmDeleteKb"
            />
          </div>
          <div class="tk-caption">
            {{ archived ? '只有已归档的知识库才能删除。' : '删除前需要先归档该知识库。' }}
          </div>
        </div>
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import KbMembersPanel from 'src/components/KbMembersPanel.vue'
import KbShareLinksPanel from 'src/components/KbShareLinksPanel.vue'
import { useKbStore } from 'src/stores/knowledge-base'
import type { ManageSection } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient } from 'src/utils/identity-client'
import type { KnowledgeBaseSummary } from 'src/utils/identity-client'

const props = withDefaults(defineProps<{
  modelValue: boolean
  kb: KnowledgeBaseSummary
  initialSection?: ManageSection
}>(), { initialSection: 'overview' })

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
const shareAnchor = ref<HTMLElement | null>(null)

watch(show, async open => {
  if (!open) return
  name.value = props.kb.name
  // The share button opens the dialog straight at the share links panel.
  if (props.initialSection === 'share' && isOwner.value) {
    await nextTick()
    shareAnchor.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }
})

function invalidateKb() {
  queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
}

async function rename() {
  const next = name.value.trim()
  if (!next || renaming.value || next === props.kb.name) return
  renaming.value = true
  try {
    const result = await identityClient.renameKnowledgeBase(props.kb.id, { name: next })
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '重命名失败') })
      return
    }
    Notify.create({ type: 'positive', message: '已重命名' })
    invalidateKb()
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '重命名失败') })
  } finally {
    renaming.value = false
  }
}

function confirmArchive() {
  $q.dialog({
    title: '归档知识库',
    message: `确定归档“${props.kb.name}”吗？成员将无法再添加或修改内容。`,
    cancel: true,
    ok: {
      label: '归档',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.archiveKnowledgeBase(props.kb.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '归档失败') })
      return
    }
    Notify.create({ type: 'positive', message: '知识库已归档' })
    invalidateKb()
  })
}

async function restore() {
  const result = await identityClient.restoreKnowledgeBase(props.kb.id)
  if (result.error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '恢复失败') })
    return
  }
  Notify.create({ type: 'positive', message: '知识库已恢复' })
  invalidateKb()
}

function confirmDeleteKb() {
  $q.dialog({
    title: '删除知识库',
    message: `确定删除“${props.kb.name}”吗？此操作无法撤销。`,
    cancel: true,
    ok: {
      label: '删除',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.deleteKnowledgeBase(props.kb.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '删除失败') })
      return
    }
    Notify.create({ type: 'positive', message: '知识库已删除' })
    show.value = false
    // Clear the selection first; the store falls back to the next knowledge
    // base once the refreshed list lands.
    kbStore.id = null
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
  })
}
</script>

<style scoped>
.kb-manage-card {
  width: min(92vw, 520px);
  border-radius: var(--tk-radius-lg);
}

.kb-manage-title {
  font-size: 17px;
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
