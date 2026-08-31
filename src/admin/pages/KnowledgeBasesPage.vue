<template>
  <q-page-container>
    <q-page p-4>
      <div
        flex
        gap-2
      >
        <q-input
          v-model="search"
          dense
          outlined
          label="搜索知识库"
        />
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
            icon="add"
            flat
            :disable="!newName || !newOwnerUserId"
            @click="create"
          />
        </template>
        <q-btn
          icon="refresh"
          flat
          @click="load"
        />
      </div>
      <q-banner
        v-if="error"
        bg-err-c
        text-on-err-c
      >
        {{ error }} <q-btn
          icon="refresh"
          flat
          @click="load"
        />
      </q-banner>
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
              icon="archive"
              flat
              @click="archive(props.row.id)"
            />
            <q-btn
              v-else
              icon="restore"
              flat
              @click="restore(props.row.id)"
            />
            <q-btn
              icon="delete"
              flat
              @click="remove(props.row.id)"
            />
          </q-td>
        </template>
      </q-table>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient, session } from 'src/utils/identity-client'

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
