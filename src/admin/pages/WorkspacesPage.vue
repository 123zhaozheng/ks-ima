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
          label="Search workspaces"
        />
        <template v-if="canManage">
          <q-input
            v-model="newName"
            dense
            outlined
            label="New workspace"
          />
          <q-input
            v-model="newAdminUserId"
            dense
            outlined
            label="Initial workspace admin user ID"
          />
          <q-btn
            icon="add"
            flat
            :disable="!newName"
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

type Workspace = components['schemas']['WorkspaceInfo']
const rows = ref<Workspace[]>([])
const search = ref('')
const newName = ref('')
const newAdminUserId = ref('')
const loading = ref(false)
const error = ref('')
const canManage = computed(() => session.value.data?.user.platformRoles?.some(role => role === 'super_admin' || role === 'platform_admin') ?? false)
const columns: QTableColumn[] = [
  { name: 'name', label: 'Name', field: 'name', align: 'left' },
  { name: 'status', label: 'Status', field: row => row.isActive ? 'Active' : 'Archived' },
  { name: 'created', label: 'Created', field: row => new Date(row.createdAt).toLocaleString() },
  { name: 'actions', label: 'Actions', field: 'id' },
]

async function create() {
  const result = await identityClient.createWorkspace({ name: newName.value, initialAdminUserId: newAdminUserId.value })
  if (result.error) { error.value = result.error.message; return }
  newName.value = ''
  newAdminUserId.value = ''
  await load()
}
async function archive(id: string) { const result = await identityClient.archiveWorkspace(id); if (result.error) error.value = result.error.message; else await load() }
async function restore(id: string) { const result = await identityClient.restoreWorkspace(id); if (result.error) error.value = result.error.message; else await load() }
async function remove(id: string) { const result = await identityClient.deleteWorkspace(id); if (result.error) error.value = result.error.message; else await load() }

async function load() {
  loading.value = true
  error.value = ''
  const result = await identityClient.listWorkspaces(search.value)
  rows.value = result.data?.items ?? []
  if (result.error) error.value = result.error.message
  loading.value = false
}
load().catch(() => undefined)
</script>
