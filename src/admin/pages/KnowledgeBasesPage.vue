<template>
  <div>
    <div class="admin-toolbar">
      <q-input
        v-model="search"
        dense
        outlined
        label="搜索知识库"
      >
        <template #prepend>
          <q-icon
            name="sym_o_search"
            size="18px"
          />
        </template>
      </q-input>
      <template v-if="canManage">
        <q-input
          v-model="newName"
          dense
          outlined
          label="新建知识库"
        />
        <q-input
          v-model="newOwnerUserId"
          dense
          outlined
          label="初始所有者用户 ID"
        />
        <q-btn
          class="tk-btn-primary"
          unelevated
          no-caps
          icon="sym_o_add"
          :disable="!newName || !newOwnerUserId"
          @click="create"
        >
          新建
        </q-btn>
      </template>
      <q-btn
        class="tk-btn-ghost"
        flat
        no-caps
        icon="sym_o_refresh"
        label="刷新"
        ml-a
        @click="load"
      />
    </div>
    <div
      v-if="error"
      class="admin-banner admin-banner-error"
      mt-2
    >
      {{ error }} <q-btn
        icon="refresh"
        flat
        dense
        @click="load"
      />
    </div>
    <q-table
      :rows="rows"
      :columns="columns"
      row-key="id"
      flat
      mt-4
      :loading="loading"
    >
      <template #body-cell-actions="props">
        <q-td v-if="canManage">
          <q-btn
            v-if="props.row.isActive"
            class="tk-btn-ghost"
            icon="sym_o_archive"
            flat
            no-caps
            label="归档"
            @click="archive(props.row.id)"
          />
          <q-btn
            v-else
            class="tk-btn-ghost"
            icon="sym_o_restore_from_trash"
            flat
            no-caps
            label="恢复"
            @click="restore(props.row.id)"
          />
          <q-btn
            class="tk-btn-danger-ghost"
            icon="sym_o_delete"
            flat
            no-caps
            label="删除"
            @click="remove(props.row.id)"
          />
        </q-td>
      </template>
      <template #no-data>
        <pane-empty-state
          icon="sym_o_folder_open"
          title="暂无知识库"
        />
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient, session } from 'src/utils/identity-client'
import PaneEmptyState from 'src/components/PaneEmptyState.vue'

type KnowledgeBaseInfo = components['schemas']['KnowledgeBaseInfo']
const rows = ref<KnowledgeBaseInfo[]>([])
const search = ref('')
const newName = ref('')
const newOwnerUserId = ref('')
const loading = ref(false)
const error = ref('')
const canManage = computed(() => session.value.data?.user.platformRoles?.some(role => role === 'super_admin' || role === 'platform_admin') ?? false)
const columns: QTableColumn[] = [
  { name: 'name', label: '名称', field: 'name', align: 'left' },
  { name: 'status', label: '状态', field: row => row.isActive ? '启用' : '已归档' },
  { name: 'created', label: '创建时间', field: row => new Date(row.createdAt).toLocaleString() },
  { name: 'actions', label: '操作', field: 'id' },
]

async function create() {
  const result = await identityClient.adminCreateKnowledgeBase({ name: newName.value, initialOwnerUserId: newOwnerUserId.value })
  if (result.error) { error.value = result.error.message; return }
  newName.value = ''
  newOwnerUserId.value = ''
  await load()
}
async function archive(id: string) { const result = await identityClient.adminArchiveKnowledgeBase(id); if (result.error) error.value = result.error.message; else await load() }
async function restore(id: string) { const result = await identityClient.adminRestoreKnowledgeBase(id); if (result.error) error.value = result.error.message; else await load() }
async function remove(id: string) { const result = await identityClient.adminDeleteKnowledgeBase(id); if (result.error) error.value = result.error.message; else await load() }

async function load() {
  loading.value = true
  error.value = ''
  const result = await identityClient.adminListKnowledgeBases(search.value)
  rows.value = result.data?.items ?? []
  if (result.error) error.value = result.error.message
  loading.value = false
}
load().catch(() => undefined)
</script>
