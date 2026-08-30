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
      <q-toolbar-title>{{ t('Knowledge base') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="userId && !workspaceStore.id"
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
          {{ t('Your knowledge base lives in a workspace') }}
        </div>
        <div class="tk-empty-subtitle">
          {{ t('Create a workspace to start collecting notes and files, or join one with an invitation.') }}
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            :label="t('Create Workspace')"
            data-testid="kb-create-workspace"
            @click="showCreateWorkspace = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            :label="t('Join workspace')"
            data-testid="kb-join-workspace"
            @click="joinWorkspace"
          />
        </div>
      </div>
    </q-page>
    <q-page
      v-else-if="workspaceStore.id"
      class="kb-page"
      :style-fn="pageFhStyle"
    >
      <aside
        class="kb-tree-pane"
        data-testid="kb-tree-pane"
      >
        <div class="kb-pane-header">
          <span class="kb-pane-title">{{ t('Folders') }}</span>
          <q-btn
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
            flat
            dense
            icon="sym_o_note_add"
            :label="t('New note')"
            :disable="!folderId"
            data-testid="kb-new-note"
            @click="activeDialog = 'note'"
          />
          <q-btn
            flat
            dense
            icon="sym_o_upload_file"
            :label="t('Upload')"
            :disable="!folderId"
            data-testid="kb-upload"
            @click="activeDialog = 'upload'"
          />
          <q-space />
          <q-select
            v-model="tagFilter"
            dense
            outlined
            options-dense
            emit-value
            map-options
            clearable
            :options="tagOptions"
            :label="t('Tags')"
            class="kb-tag-filter"
            data-testid="kb-tag-filter"
          />
        </div>
        <knowledge-list
          :folder-id="folderId"
          :selected-id="documentId"
          :tag-id="tagFilter"
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
          @close="previewCollapsed = true"
          @trashed="onTrashed"
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
    </q-page>
  </q-page-container>
  <new-folder-dialog
    :model-value="activeDialog === 'folder'"
    :workspace-id="workspaceStore.id ?? ''"
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
  <create-workspace-dialog v-model="showCreateWorkspace" />
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, ref, useTemplateRef, watch } from 'vue'
import { useQuasar } from 'quasar'
import { useRoute, useRouter } from 'vue-router'
import CreateNoteDialog from 'src/components/CreateNoteDialog.vue'
import CreateWorkspaceDialog from 'src/components/CreateWorkspaceDialog.vue'
import DocPreview from 'src/components/DocPreview.vue'
import FolderTree from 'src/components/FolderTree.vue'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import NewFolderDialog from 'src/components/NewFolderDialog.vue'
import UploadDialog from 'src/components/UploadDialog.vue'
import { useKnowledgeTags } from 'src/composables/use-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useUiStateStore } from 'src/stores/ui-state'
import { useWorkspaceStore } from 'src/stores/workspace'
import { pageFhStyle } from 'src/utils/functions'
import { session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'

type Folder = components['schemas']['Folder']
type Document = components['schemas']['DocumentResponse']

useRequireLogin()

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()

const userId = computed(() => session.value.data?.user.id)
const listReady = computed(() => workspaceStore.workspacesStatus === 'success')

// The workspace root folder is the workspace itself; subfolders and the
// selected document live in the shareable ?folderId= / ?doc= query params.
const folderId = computed(() => {
  const query = route.query.folderId
  return typeof query === 'string' && query ? query : workspaceStore.id ?? ''
})
const documentId = computed(() => {
  const query = route.query.doc
  return typeof query === 'string' && query ? query : null
})

const treeRef = useTemplateRef<InstanceType<typeof FolderTree>>('treeRef')
// Only one KB dialog may be open at a time; they previously stacked.
const activeDialog = ref<'folder' | 'note' | 'upload' | null>(null)
const showCreateWorkspace = ref(false)
const previewCollapsed = ref(true)
// One-shot: a freshly created note opens straight in the editor.
const editDocId = ref<string>()

function joinWorkspace() {
  $q.dialog({
    title: t('Join Workspace'),
    prompt: {
      model: '',
      label: t('Invitation Link'),
    },
    cancel: true,
  }).onOk((link: string) => {
    const token = link.match(/\/invitations\/(.+)/)?.[1]
    token && router.push(`/invitations/${token}`)
  })
}

const tagFilter = ref<string | null>(null)
const tags = useKnowledgeTags(() => workspaceStore.id)
const tagOptions = computed(() => (tags.data.value ?? []).map(tag => ({ label: tag.name, value: tag.id })))

watch(documentId, id => {
  if (id) previewCollapsed.value = false
}, { immediate: true })

watch(() => workspaceStore.id, (id, previous) => {
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

function onTrashed() {
  editDocId.value = undefined
  router.replace({ path: '/kb', query: folderId.value ? { folderId: folderId.value } : {} })
}
</script>

<style scoped>
.kb-header {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.kb-page {
  display: flex;
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

.kb-tag-filter {
  width: 168px;
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
