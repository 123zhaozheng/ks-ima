<template>
  <!-- KB role badges and the share entry live in the shell TopBar. -->
  <teleport
    defer
    to="#topbar-actions"
  >
    <q-badge
      v-if="isViewer"
      outline
      color="primary"
      class="kb-role-badge"
    >
      只读
    </q-badge>
    <q-badge
      v-if="isArchived"
      outline
      color="warning"
      class="kb-role-badge"
    >
      已归档
    </q-badge>
    <q-btn
      v-if="kbStore.isOwner"
      flat
      dense
      no-caps
      icon="sym_o_ios_share"
      label="分享"
      data-testid="kb-manage"
      @click="kbStore.openManage('share')"
    />
  </teleport>
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
          创建你的第一个知识库
        </div>
        <div class="tk-empty-subtitle">
          创建一个知识库，收集笔记和文件；也可以通过分享链接加入别人的知识库。
        </div>
        <div class="tk-empty-actions">
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            label="新建知识库"
            data-testid="kb-create"
            @click="showCreateKb = true"
          />
          <q-btn
            flat
            no-caps
            class="tk-cta-secondary"
            label="通过链接加入"
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
        你的角色为只读，只能浏览此知识库的内容，无法修改。
      </div>
      <div
        v-if="isArchived"
        class="kb-banner"
      >
        该知识库已归档，无法再更改。
      </div>
      <div class="kb-page-body">
        <aside
          v-show="!(isNarrow && treeCollapsed)"
          class="kb-tree-pane"
          data-testid="kb-tree-pane"
        >
          <div class="kb-pane-header">
            <span class="kb-pane-title">文件夹</span>
            <q-btn
              v-if="canWrite"
              flat
              dense
              round
              icon="sym_o_create_new_folder"
              title="新建文件夹"
              data-testid="kb-new-folder"
              @click="activeDialog = 'folder'"
            />
          </div>
          <folder-tree ref="treeRef" />
        </aside>
        <section class="kb-list-pane">
          <div class="kb-pane-header kb-list-header">
            <q-btn
              v-if="isNarrow"
              flat
              dense
              round
              icon="sym_o_menu"
              title="文件夹"
              aria-label="文件夹"
              data-testid="kb-tree-toggle"
              @click="treeCollapsed = !treeCollapsed"
            />
            <nav
              class="kb-breadcrumb"
              aria-label="所在位置"
            >
              <button
                type="button"
                class="kb-breadcrumb-root"
                @click="goRoot"
              >
                全部资料
              </button>
              <template v-if="currentFolderTitle">
                <q-icon
                  name="sym_o_chevron_right"
                  size="14px"
                  class="kb-breadcrumb-sep"
                />
                <span class="kb-breadcrumb-current">{{ currentFolderTitle }}</span>
              </template>
            </nav>
            <q-btn
              v-if="canWrite"
              unelevated
              no-caps
              class="tk-btn-secondary"
              icon="sym_o_note_add"
              label="新建笔记"
              :disable="!folderId"
              data-testid="kb-new-note"
              @click="activeDialog = 'note'"
            />
            <q-btn
              v-if="canWrite"
              unelevated
              no-caps
              class="tk-btn-secondary"
              icon="sym_o_upload_file"
              label="上传"
              :disable="!folderId"
              data-testid="kb-upload"
              @click="activeDialog = 'upload'"
            />
            <q-btn
              flat
              dense
              round
              icon="sym_o_swap_vert"
              title="排序"
              aria-label="排序"
              data-testid="kb-sort"
            >
              <q-menu>
                <q-list dense>
                  <q-item-label header>
                    分组
                  </q-item-label>
                  <q-item
                    v-for="opt in groupOptions"
                    :key="opt.value"
                    v-close-popup
                    clickable
                    :data-testid="`kb-sort-group-${opt.value}`"
                    @click="listSort.group = opt.value"
                  >
                    <q-item-section
                      avatar
                      min-w-0
                    >
                      <q-icon
                        v-if="listSort.group === opt.value"
                        name="sym_o_check"
                        color="primary"
                      />
                    </q-item-section>
                    <q-item-section>{{ opt.label }}</q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item-label header>
                    排序
                  </q-item-label>
                  <q-item
                    v-for="opt in sortOptions"
                    :key="opt.value"
                    v-close-popup
                    clickable
                    :data-testid="`kb-sort-by-${opt.value}`"
                    @click="listSort.sort = opt.value"
                  >
                    <q-item-section
                      avatar
                      min-w-0
                    >
                      <q-icon
                        v-if="listSort.sort === opt.value"
                        name="sym_o_check"
                        color="primary"
                      />
                    </q-item-section>
                    <q-item-section>{{ opt.label }}</q-item-section>
                  </q-item>
                </q-list>
              </q-menu>
            </q-btn>
          </div>
          <knowledge-list
            :folder-id="folderId"
            :selected-id="documentId"
            :readonly="!canWrite"
            :sort="listSort.sort"
            :group="listSort.group"
          />
        </section>
        <div
          v-if="isNarrow && documentId && !previewCollapsed"
          class="kb-preview-backdrop"
          @click="previewCollapsed = true"
        />
        <section
          v-if="!previewCollapsed"
          class="kb-preview-pane"
          :class="{ 'kb-preview-drawer': isNarrow && documentId }"
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
            min-h-0
          >
            <pane-empty-state
              icon="sym_o_visibility"
              title="选择一篇文档以预览"
            />
          </div>
        </section>
        <div
          v-else
          class="kb-preview-reopen"
          role="button"
          title="预览"
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
  <q-dialog
    v-model="showCreateKb"
    @hide="newKbName = ''"
  >
    <q-card min-w="360px">
      <q-card-section class="text-h6">
        新建知识库
      </q-card-section>
      <q-card-section>
        <q-input
          v-model="newKbName"
          outlined
          autofocus
          label="知识库名称"
          data-testid="kb-name-input"
          @keyup.enter="createKb"
        />
        <div class="tk-caption q-mt-sm">
          你将成为新知识库的所有者。
        </div>
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
import { computed, onBeforeUnmount, ref, useTemplateRef, watch } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import { useRoute, useRouter } from 'vue-router'
import CreateNoteDialog from 'src/components/CreateNoteDialog.vue'
import DocPreview from 'src/components/DocPreview.vue'
import FolderTree from 'src/components/FolderTree.vue'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import PaneEmptyState from 'src/components/PaneEmptyState.vue'
import NewFolderDialog from 'src/components/NewFolderDialog.vue'
import UploadDialog from 'src/components/UploadDialog.vue'
import { useRequireLogin } from 'src/composables/require-login'
import { useFolderContents } from 'src/composables/use-knowledge'
import { useKbListSort } from 'src/composables/use-kb-list-sort'
import type { KbListGroup, KbListSort } from 'src/api/knowledge-client'
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { pageFhStyle } from 'src/utils/functions'
import { identityClient, session } from 'src/utils/identity-client'

type Folder = components['schemas']['Folder']
type Document = components['schemas']['DocumentResponse']

useRequireLogin()

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()

const userId = computed(() => session.value.data?.user.id)
const listReady = computed(() => kbStore.kbsStatus === 'success')

// Viewers can browse but never write; archived knowledge bases freeze writes
// for everyone until restored.
const isViewer = computed(() => kbStore.myRole === 'viewer')
const isArchived = computed(() => Boolean(kbStore.current?.archivedAt))
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

// Below 1000px the preview becomes an overlay drawer and the tree pane can
// fold away behind the list header toggle.
const narrowQuery = window.matchMedia('(max-width: 999px)')
const isNarrow = ref(narrowQuery.matches)
const treeCollapsed = ref(false)

function onNarrowChange(event: MediaQueryListEvent) {
  isNarrow.value = event.matches
}

narrowQuery.addEventListener('change', onNarrowChange)
onBeforeUnmount(() => narrowQuery.removeEventListener('change', onNarrowChange))

// The tree owns the folder map; read the current folder's title for the list
// header breadcrumb (empty at the knowledge base root).
const currentFolderTitle = computed(() => {
  const id = folderId.value
  if (!id || id === kbStore.id) return ''
  return treeRef.value?.folderTitle(id) ?? ''
})

function goRoot() {
  router.push('/kb')
}
// Only one KB dialog may be open at a time; they previously stacked.
const activeDialog = ref<'folder' | 'note' | 'upload' | null>(null)
const showCreateKb = ref(false)
const newKbName = ref('')
const creatingKb = ref(false)
const previewCollapsed = ref(true)
// One-shot: a freshly created note opens straight in the editor.
const editDocId = ref<string>()

// Folder-list sort preference (persisted); drives both the list and the
// default-preview ordering so they never disagree.
const listSort = useKbListSort()
const groupOptions: { value: KbListGroup, label: string }[] = [
  { value: 'folders_first', label: '文件夹优先' },
  { value: 'files_first', label: '文件优先' },
]
const sortOptions: { value: KbListSort, label: string }[] = [
  { value: 'manual', label: '默认排序' },
  { value: 'name_asc', label: '名称 A→Z' },
  { value: 'name_desc', label: '名称 Z→A' },
  { value: 'created_desc', label: '最新上传' },
  { value: 'created_asc', label: '最早上传' },
]

function joinWithLink() {
  $q.dialog({
    title: '加入知识库',
    prompt: {
      model: '',
      label: '分享链接',
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
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
      return
    }
    Notify.create({ type: 'positive', message: '知识库已创建' })
    showCreateKb.value = false
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.switchKb(data.id)
    router.replace('/kb')
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
  } finally {
    creatingKb.value = false
  }
}

watch(documentId, id => {
  if (id) previewCollapsed.value = false
}, { immediate: true })

// Default-preview: when the current folder has documents but the URL has no
// ?doc=, select the first previewable row so the pane never opens empty.
// Shares the list's query via the same queryKey (no extra request).
const folderContents = useFolderContents(
  () => folderId.value || null,
  () => ({ sort: listSort.sort, group: listSort.group }),
)
// Closing the preview is sticky for the folder being viewed; switching folders
// re-arms the auto-preview.
const previewDismissed = ref(false)
watch(previewCollapsed, collapsed => {
  if (collapsed) previewDismissed.value = true
})
watch(folderId, () => {
  previewDismissed.value = false
})
const firstPreviewableId = computed(() => {
  const items = folderContents.data.value?.items ?? []
  return items.find(item => item.kind !== 'folder')?.id ?? null
})
watch([documentId, firstPreviewableId, () => folderContents.isSuccess.value], ([docId, firstId, loaded]) => {
  if (docId || !loaded || !firstId || previewDismissed.value) return
  router.replace({ query: { ...route.query, doc: firstId } })
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
.kb-role-badge {
  font-weight: 400;
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
  position: relative;
  display: flex;
  flex: 1;
  min-height: 0;
}

.kb-tree-pane {
  width: 232px;
  flex: 0 0 232px;
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

.kb-breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--tk-space-1);
  flex: 1;
  min-width: 0;
  font-size: 13px;
}

.kb-breadcrumb-root {
  padding: 0;
  border: none;
  font: inherit;
  color: var(--tk-text-secondary);
  background: none;
  cursor: pointer;
  border-radius: var(--tk-radius-sm);
}

.kb-breadcrumb-root:hover {
  color: var(--tk-text);
}

.kb-breadcrumb-sep {
  flex: none;
  color: var(--tk-text-tertiary);
}

.kb-breadcrumb-current {
  min-width: 0;
  overflow: hidden;
  font-weight: var(--tk-weight-medium);
  color: var(--tk-text);
  white-space: nowrap;
  text-overflow: ellipsis;
}

.kb-list-header .tk-btn-secondary {
  min-height: 34px;
  padding: 0 var(--tk-space-3);
}

.kb-list-header :deep(.tk-btn-secondary .q-icon) {
  font-size: 16px;
}

.kb-list-pane {
  flex: 1 1 0;
  min-width: 320px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--tk-border);
  background-color: var(--tk-surface-white);
}

.kb-preview-pane {
  flex: 0 0 clamp(380px, 32vw, 480px);
  display: flex;
  flex-direction: column;
  min-height: 0;
  background-color: var(--tk-bg);
}

/* Below 1000px the preview floats over the panes as a drawer. */
.kb-preview-drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 3;
  flex: 0 0 auto;
  width: min(420px, 100%);
  background-color: var(--tk-surface-white);
  border-left: 1px solid var(--tk-border);
  box-shadow: var(--tk-shadow-lg);
  animation: kb-drawer-in var(--tk-dur-slow) var(--tk-ease-out);
}

.kb-preview-backdrop {
  position: absolute;
  inset: 0;
  z-index: 2;
  background-color: rgba(0, 0, 0, 0.32);
}

@keyframes kb-drawer-in {
  from {
    transform: translateX(100%);
  }

  to {
    transform: translateX(0);
  }
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
