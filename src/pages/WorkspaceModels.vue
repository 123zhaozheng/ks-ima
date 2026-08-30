<template>
  <q-header class="tk-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('Models') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      class="tk-page models-page"
    >
      <section class="tk-card models-card">
        <div class="models-card-head">
          <h1 class="tk-card-title">
            {{ t('Workspace capabilities') }}
          </h1>
          <p class="tk-card-subtitle">
            {{ t('Capabilities are centrally managed by a platform administrator.') }}
          </p>
        </div>
        <q-banner
          v-if="error"
          rounded
          class="models-error"
        >
          {{ error }}
          <template #action>
            <q-btn
              flat
              dense
              :label="t('Retry')"
              @click="load"
            />
          </template>
        </q-banner>
        <q-list
          separator
          :class="{ 'opacity-60': loading }"
        >
          <q-item
            v-for="capability in capabilities"
            :key="capability.workflow"
          >
            <q-item-section avatar>
              <q-icon
                :name="iconFor(capability.workflow)"
                color="primary"
              />
            </q-item-section>
            <q-item-section>
              <q-item-label>{{ capability.alias }}</q-item-label>
              <q-item-label caption>
                {{ capability.description }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <div class="row items-center q-gutter-sm">
                <q-badge :color="statusColor(capability.status)">
                  {{ capability.status }}
                </q-badge>
                <span
                  v-if="capability.version"
                  class="tk-caption"
                >v{{ capability.version }}</span>
              </div>
              <div
                v-if="capability.reason"
                class="models-reason"
              >
                {{ capability.reason }}
              </div>
            </q-item-section>
          </q-item>
          <q-item v-if="!loading && !capabilities.length">
            <q-item-section class="models-empty">
              {{ t('No capabilities are assigned yet.') }}
            </q-item-section>
          </q-item>
        </q-list>
        <q-inner-loading :showing="loading">
          <q-spinner
            color="primary"
            size="2em"
          />
        </q-inner-loading>
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import type { components } from 'src/api/generated/schema'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'

type Capability = components['schemas']['WorkspaceCapability']
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()
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

<style scoped>
.models-card {
  position: relative;
}

.models-card-head {
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.models-error {
  margin: 0 var(--tk-space-4);
  background-color: var(--tk-danger-soft);
  color: var(--tk-danger);
}

.models-reason {
  font-size: 12px;
  color: var(--tk-danger);
  margin-top: var(--tk-space-1);
}

.models-empty {
  color: var(--tk-text-secondary);
}
</style>
