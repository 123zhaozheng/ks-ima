<template>
  <q-page-container>
    <q-page p-4>
      <q-table
        :rows="rows"
        :columns="columns"
        row-key="id"
        flat
        :loading="loading"
      />
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { QTableColumn } from 'quasar'
import type { components } from 'src/api/generated/schema'
import { identityClient } from 'src/utils/identity-client'

type AuditEvent = components['schemas']['AuditEvent']
const rows = ref<AuditEvent[]>([])
const loading = ref(true)
const columns: QTableColumn[] = [
  { name: 'createdAt', label: 'Time', field: 'createdAt' },
  { name: 'action', label: 'Action', field: 'action' },
  { name: 'target', label: 'Target', field: row => `${row.targetType ?? ''}/${row.targetId ?? ''}` },
  { name: 'result', label: 'Result', field: 'result' },
]
identityClient.listAudit().then(result => {
  rows.value = result.data?.items ?? []
}).finally(() => {
  loading.value = false
})
</script>
