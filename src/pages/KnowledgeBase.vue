<template>
  <q-header class="kb-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ kbStore.kb?.name ?? t('Knowledge base') }}</q-toolbar-title>
      <q-badge
        v-if="isViewer"
        outline
        color="primary"
        class="kb-role-badge"
      >
        {{ t('Read only') }}
      </q-badge>
      <q-badge
        v-if="isArchived"
        outline
        color="warning"
        class="kb-role-badge"
      >
        {{ t('Archived') }}
      </q-badge>
      <q-btn
        v-if="kbStore.kb"
        flat
        dense
        round
        icon="sym_o_group"
        :title="t('Members and sharing')"
        data-testid="kb-manage"
        @click="showManage = true"
      />
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="userId && !kbStore.id"
      flex
      flex-center
      text-on-sur-var
    >
      <q-spinner
        v-if="!listReady"
        color="primary"
        size="40px"
      />
      <div
        v-else
        class="tk-empty"
        data-testid="kb-onboarding"
      >
        <q-icon
          name="sym_o_folder_open"
          size="56px"
          class="tk-empty-icon"
        />
        <div class="tk-empty-title">
          {{ t('Create your first knowledge base') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Create a knowledge base to collect notes and files, or join one shared with you.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create knowledge base')"
            data-testid="kb-create"
            @click="showCreateKb = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join with a link')"
            data-testid="kb-join"
            @click="joinWithLink"
          />
        </div>
      </div>
    </q-page>
    <q-page
      v-else-if="kbStore.id"
      class="kb-page"
      :style-fn="pageFhStyle"
    >
      <div
        v-if="isViewer"
        class="kb-banner"
      >
        {{ t('Your role is read-only; you can browse the content in this knowledge base but cannot make changes.') }}
      </div>
      <div
        v-if="isArchived"
        class="kb-banner"
      >
        {{ t('This knowledge base is archived and can no longer be changed.') }}
      </div>
      <div class="kb-page-body">
        <aside
          class="kb-tree-pane"
          data-testid="kb-tree-pane"
        >
          <div class="kb-pane-header">
            <span class="kb-pane-title">{{ t('Folders') }}</span>
            <q-btn
              v-if="canWrite"
              flat
              dense
              round
              icon="sym_o_create_new_folder"
              :title="t('New folder')"
              data-testid="kb-new-folder"
              @click="activeDialog = 'folder'"
            />
          </div>
          <folder-tree ref="treeRef" />
        </aside>
        <section class="kb-list-pane">
          <div class="kb-pane-header">
            <q-btn
              v-if="canWrite"
              flat
              dense
              icon="sym_o_note_add"
              :label="t('New note')"
              :disable="!folderId"
              data-testid="kb-new-note"
              @click="activeDialog = 'note'"
            />
            <q-btn
              v-if="canWrite"
              flat
              dense
              icon="sym_o_upload_file"
              :label="t('Upload')"
              :disable="!folderId"
              data-testid="kb-upload"
              @click="activeDialog = 'upload'"
            />
          </div>
          <knowledge-list
            :folder-id="folderId"
            :selected-id="documentId"
            :readonly="!canWrite"
          />
        </section>
        <section
          v-if="!previewCollapsed"
          class="kb-preview-pane"
          data-testid="kb-preview-pane"
        >
          <doc-preview
            v-if="documentId"
            :document-id="documentId"
            :start-in-edit="editDocId === documentId"
            :readonly="!canWrite"
            @close="previewCollapsed = true"
            @deleted="onDeleted"
          />
          <div
            v-else
            flex="~ col"
            flex-1
            items-center
            justify-center
            gap-2
            p-6
            text-on-sur-var
          >
            <q-icon
              name="sym_o_visibility"
              size="40px"
            />
            <div>{{ t('Select a document to preview') }}</div>
          </div>
        </section>
        <div
          v-else
          class="kb-preview-reopen"
          role="button"
          :title="t('Preview')"
          data-testid="kb-preview-reopen"
          @click="previewCollapsed = false"
        >
          <q-icon name="sym_o_chevron_left" />
        </div>
      </div>
    </q-page>
  </q-page-container>
  <new-folder-dialog
    :model-value="activeDialog === 'folder'"
    :kb-id="kbStore.id ?? ''"
    :parent-folder-id="folderId"
    @update:model-value="open => (activeDialog = open ? 'folder' : null)"
    @created="onFolderCreated"
  />
  <create-note-dialog
    :model-value="activeDialog === 'note'"
    :folder-id="folderId"
    @update:model-value="open => (activeDialog = open ? 'note' : null)"
    @created="onNoteCreated"
  />
  <upload-dialog
    :model-value="activeDialog === 'upload'"
    :folder-id="folderId"
    @update:model-value="open => (activeDialog = open ? 'upload' : null)"
  />
  <kb-manage-dialog
    v-if="kbStore.kb"
    v-model="showManage"
    :kb="kbStore.kb"
  />
  <q-dialog
    v-model="showCreateKb"
    @hide="newKbName = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        {{ t('Create knowledge base') }}
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="newKbName"
          outlined
          autofocus
          :label="t('Knowledge base name')"
          data-testid="kb-name-input"
          @keyup.enter="createKb"
        />
        <div class="tk-caption q-mt-sm">
          {{ t('You will become the owner of the new knowledge base.') }}
        </div>
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
          :loading="creatingKb"
          :disable="!newKbName.trim()"
          data-testid="kb-create-button"
          @click="createKb"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, ref, useTemplateRef, watch } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import CreateNoteDialog from 'src/components/CreateNoteDialog.vue'
import DocPreview from 'src/components/DocPreview.vue'
import FolderTree from 'src/components/FolderTree.vue'
import KbManageDialog from 'src/components/KbManageDialog.vue'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import NewFolderDialog from 'src/components/NewFolderDialog.vue'
import UploadDialog from 'src/components/UploadDialog.vue'
import { useRequireLogin } from 'src/composables/require-login'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'
import { apiErrorMessage } from 'src/utils/api-error'
import { pageFhStyle } from 'src/utils/functions'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type Folder = components['schemas']['Folder']
type Document = components['schemas']['DocumentResponse']

useRequireLogin()

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()
const uiStateStore = useUiStateStore()

const userId = computed(() => session.value.data?.user.id)
const listReady = computed(() => kbStore.kbsStatus === 'success')

// Viewers can browse but never write; archived knowledge bases freeze writes
// for everyone until restored.
const isViewer = computed(() => kbStore.myRole === 'viewer')
const isArchived = computed(() => Boolean(kbStore.kb?.archivedAt))
const canWrite = computed(() => Boolean(kbStore.id) && !isViewer.value && !isArchived.value)

// The knowledge base root folder is the knowledge base itself; subfolders and
// the selected document live in the shareable ?folderId= / ?doc= query params.
const folderId = computed(() => {
  const query = route.query.folderId
  return typeof query === 'string' && query ? query : kbStore.id ?? ''
})
const documentId = computed(() => {
  const query = route.query.doc
  return typeof query === 'string' && query ? query : null
})

const treeRef = useTemplateRef<InstanceType<typeof FolderTree>>('treeRef')
// Only one KB dialog may be open at a time; they previously stacked.
const activeDialog = ref<'folder' | 'note' | 'upload' | null>(null)
const showManage = ref(false)
const showCreateKb = ref(false)
const newKbName = ref('')
const creatingKb = ref(false)
const previewCollapsed = ref(true)
// One-shot: a freshly created note opens straight in the editor.
const editDocId = ref<string>()

function joinWithLink() {
  $q.dialog({
    title: t('Join knowledge base'),
    prompt: {
      model: '',
      label: t('Share link'),
    },
    cancel: true,
  }).onOk((link: string) => {
    const token = link.match(/\/join\/(.+)/)?.[1] ?? link.trim()
    token && router.push(`/join/${encodeURIComponent(token)}`)
  })
}

async function createKb() {
  const name = newKbName.value.trim()
  if (!name || creatingKb.value) return
  creatingKb.value = true
  try {
    const { data, error } = await identityClient.createKnowledgeBase({ name })
    if (error || !data) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Knowledge base created') })
    showCreateKb.value = false
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.switchKb(data.id)
    router.replace('/kb')
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
  } finally {
    creatingKb.value = false
  }
}

watch(documentId, id => {
  if (id) previewCollapsed.value = false
}, { immediate: true })

watch(() => kbStore.id, (id, previous) => {
  if (!id || !previous || id === previous) return
  if (route.query.folderId || route.query.doc) router.replace({ query: {} })
}, { immediate: true })

async function onFolderCreated(folder: Folder) {
  await treeRef.value?.refresh(folder.parentId ?? undefined)
  router.push({ path: '/kb', query: { folderId: folder.id } })
}

function onNoteCreated(document: Document) {
  editDocId.value = document.id
  router.push({ path: '/kb', query: { folderId: document.folderId, doc: document.id } })
}

function onDeleted() {
  editDocId.value = undefined
  router.replace({ path: '/kb', query: folderId.value ? { folderId: folderId.value } : {} })
}
</script>

<style scoped>
.kb-header {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.kb-role-badge {
  font-weight: 400;
  margin-right: var(--tk-space-2);
}

.kb-page {
  display: flex;
  flex-direction: column;
}

.kb-banner {
  padding: var(--tk-space-2) var(--tk-space-4);
  font-size: 13px;
  color: var(--tk-text-secondary);
  background-color: var(--tk-surface);
  border-bottom: 1px solid var(--tk-border);
}

.kb-page-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.kb-tree-pane {
  width: 240px;
  flex: 0 0 240px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background-color: var(--tk-surface);
  border-right: 1px solid var(--tk-border);
}

.kb-pane-header {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  padding: var(--tk-space-2) var(--tk-space-3);
  border-bottom: 1px solid var(--tk-border);
}

.kb-pane-title {
  flex: 1;
  font-size: 13px;
  color: var(--tk-text-secondary);
}

.kb-list-pane {
  flex: 1 1 0;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--tk-border);
  background-color: var(--tk-bg);
}

.kb-preview-pane {
  flex: 1 1 0;
  min-width: 380px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background-color: var(--tk-bg);
}

.kb-preview-reopen {
  flex: 0 0 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  background-color: var(--tk-surface);
  border-left: 1px solid var(--tk-border);
  color: var(--tk-text-secondary);
}
</style>
