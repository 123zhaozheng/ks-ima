<template>
  <q-page-container>
    <q-page v-if="workspaceStore.id" class="q-pa-lg" style="max-width: 800px; margin: auto">
      <div class="text-h6 q-mb-xs">{{ t('Workspace capabilities') }}</div>
      <div class="text-caption text-grey-7 q-mb-lg">{{ t('Capabilities are centrally managed by a platform administrator.') }}</div>
      <q-banner v-if="error" class="bg-red-1 text-negative q-mb-md" rounded>
        {{ error }}
        <template #action><q-btn flat :label="t('Retry')" @click="load" /></template>
      </q-banner>
      <q-list bordered separator :class="{ 'opacity-60': loading }">
        <q-item v-for="capability in capabilities" :key="capability.workflow">
          <q-item-section avatar><q-icon :name="iconFor(capability.workflow)" color="primary" /></q-item-section>
          <q-item-section>
            <q-item-label>{{ capability.alias }}</q-item-label>
            <q-item-label caption>{{ capability.description }}</q-item-label>
          </q-item-section>
          <q-item-section side>
            <div class="row items-center q-gutter-sm">
              <q-badge :color="statusColor(capability.status)">{{ capability.status }}</q-badge>
              <span v-if="capability.version" class="text-caption">v{{ capability.version }}</span>
            </div>
            <div v-if="capability.reason" class="text-caption text-negative q-mt-xs">{{ capability.reason }}</div>
          </q-item-section>
        </q-item>
        <q-item v-if="!loading && !capabilities.length"><q-item-section class="text-grey-7">{{ t('No capabilities are assigned yet.') }}</q-item-section></q-item>
      </q-list>
      <q-inner-loading :showing="loading"><q-spinner color="primary" size="2em" /></q-inner-loading>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { components } from 'src/api/generated/schema'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'

type Capability = components['schemas']['WorkspaceCapability']
const workspaceStore = useWorkspaceStore()
const capabilities = ref<Capability[]>([])
const loading = ref(false)
const error = ref('')
async function load() {
  if (!workspaceStore.id) return
  loading.value = true
  const result = await identityClient.workspaceCapabilities(workspaceStore.id)
  capabilities.value = result.data ?? []
  error.value = result.error?.message ?? ''
  loading.value = false
}
function statusColor(status: Capability['status']) { return status === 'available' ? 'positive' : status === 'degraded' ? 'warning' : 'negative' }
function iconFor(workflow: Capability['workflow']) { return workflow === 'grounded_ask' ? 'sym_o_question_answer' : workflow === 'embedding' ? 'sym_o_hub' : workflow === 'reranking' ? 'sym_o_sort' : 'sym_o_auto_awesome' }
watch(() => workspaceStore.id, load)
onMounted(load)
</script>
