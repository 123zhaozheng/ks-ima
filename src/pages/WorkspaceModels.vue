<template>
  <q-page-container>
    <q-page
      v-if="workspaceStore.id"
      max-w="800px"
      mx-a
      py-2
    >
      <q-list>
        <q-item-label header>
          {{ t('Intranet gateway') }}
        </q-item-label>
        <q-item>
          <q-item-section>
            <q-item-label>
              {{ t('Add an OpenAI-compatible gateway. Chat and embedding should only call this address.') }}
            </q-item-label>
            <q-item-label caption>
              {{ t('Open a gateway to add model names used for Ask, embedding, and rerank.') }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-btn
              unelevated
              no-caps
              color="primary"
              :label="t('Add gateway')"
              @click="addGateway"
            />
          </q-item-section>
        </q-item>
        <q-item
          v-for="provider in providers"
          :key="provider.id"
          clickable
          :to="`/provider/${provider.id}`"
        >
          <q-item-section>
            <q-item-label>
              {{ provider.entity?.name || t('OpenAI Compatible') }}
            </q-item-label>
            <q-item-label caption>
              {{ t('Models') }} · {{ provider.models?.length ?? 0 }}
            </q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-icon name="sym_o_chevron_right" />
          </q-item-section>
        </q-item>
        <q-item
          v-if="!providers.length"
          text-on-sur-var
        >
          <q-item-section>
            {{ t('No gateway yet. Add one so Ask can run.') }}
          </q-item-section>
        </q-item>

        <q-separator spaced />
        <q-item-label header>
          {{ t('Ask and retrieval') }}
        </q-item-label>
        <common-item
          :label="t('Default Ask model')"
          :caption="t('Used for new Ask conversations. You can still change it in a chat.')"
        >
          <model-select
            :workspace-id="workspaceStore.id"
            v-model="chatModelId"
            dense
            filled
            class="min-w-220px"
          />
        </common-item>
        <common-item
          :label="t('Embedding model')"
          :caption="embeddingCaption"
        >
          <model-select
            :workspace-id="workspaceStore.id"
            v-model="embeddingModelId"
            clearable
            dense
            filled
            class="min-w-220px"
          />
        </common-item>
        <common-item
          :label="t('Retrieval')"
          :caption="t('How Ask finds passages. Hybrid uses keyword and vector together.')"
        >
          <q-btn-toggle
            :model-value="searchMode"
            @update:model-value="searchMode = $event"
            unelevated
            no-caps
            toggle-color="primary"
            :options="searchModeOptions"
          />
        </common-item>
        <common-item
          :label="t('Rerank model')"
          :caption="t('Optional. Reorders retrieved passages. Leave empty to skip.')"
        >
          <model-select
            :workspace-id="workspaceStore.id"
            v-model="rerankModelId"
            clearable
            dense
            filled
            class="min-w-220px"
          />
        </common-item>
        <common-item
          :label="t('Passages to retrieve')"
          :caption="t('How many passages Ask keeps. Default 8.')"
        >
          <q-input
            :model-value="topK"
            @update:model-value="topK = Number($event) || 8"
            type="number"
            min="1"
            max="30"
            dense
            filled
            class="w-100px"
          />
        </common-item>
        <common-item
          v-if="searchMode === 'hybrid'"
          :label="t('Vector weight')"
          :caption="t('Dify hybrid: this share is semantic, the rest is keyword. Default 0.7.')"
        >
          <q-input
            :model-value="vectorWeight"
            @update:model-value="vectorWeight = Number($event) || 0.7"
            type="number"
            min="0"
            max="1"
            step="0.05"
            dense
            filled
            class="w-100px"
          />
        </common-item>
        <common-item
          :label="t('Score threshold')"
          :caption="t('Drop passages below this 0–1 score after fusion or rerank. 0 keeps all.')"
        >
          <q-input
            :model-value="scoreThreshold"
            @update:model-value="scoreThreshold = Number($event) || 0"
            type="number"
            min="0"
            max="1"
            step="0.05"
            dense
            filled
            class="w-100px"
          />
        </common-item>
        <common-item
          :label="t('Chunk size')"
          :caption="t('Characters per passage when parsing files. Default 600. Changing this requires reindexing.')"
        >
          <q-input
            :model-value="chunkSize"
            @update:model-value="chunkSize = Number($event) || 600"
            type="number"
            min="200"
            max="2000"
            step="50"
            dense
            filled
            class="w-100px"
          />
        </common-item>
        <common-item
          :label="t('Chunk overlap')"
          :caption="t('Characters shared between neighboring passages. Default 80.')"
        >
          <q-input
            :model-value="chunkOverlap"
            @update:model-value="chunkOverlap = Number($event) || 0"
            type="number"
            min="0"
            max="500"
            step="10"
            dense
            filled
            class="w-100px"
          />
        </common-item>
        <q-item>
          <q-item-section>
            <q-btn
              unelevated
              no-caps
              :loading="reindexing"
              :label="t('Reindex all files')"
              @click="reindex"
            />
            <q-item-label caption>
              {{ t('Re-chunk and re-embed every parsed file with the current settings.') }}
            </q-item-label>
          </q-item-section>
        </q-item>

        <q-separator spaced />
        <q-item-label header>
          {{ t('Platform models') }}
        </q-item-label>
        <q-item
          v-for="model in publicModels"
          :key="model.id"
        >
          <q-item-section>
            <q-item-label>{{ model.label || model.name }}</q-item-label>
            <q-item-label caption>
              {{ model.name }}
            </q-item-label>
          </q-item-section>
        </q-item>
        <q-item
          v-if="!publicModels.length"
          text-on-sur-var
        >
          <q-item-section>
            {{ t('No platform models. The admin can add them in the admin app under Models.') }}
          </q-item-section>
        </q-item>
      </q-list>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { queries } from 'app/src-shared/queries'
import { mutators } from 'app/src-shared/mutators'
import { parseKbChunkOverlap, parseKbChunkSize, parseKbScoreThreshold, parseKbSearchMode, parseKbTopK, parseKbVectorWeight, type KbSearchMode } from 'app/src-shared/kb-settings'
import { useQuery } from 'src/composables/zero/query'
import { useRootEntityConf } from 'src/composables/entity-conf'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useLocalEntitiesStore } from 'src/stores/local-entities'
import { createEntity } from 'src/utils/create-entity'
import { systemFolderId } from 'src/utils/knowledge'
import { t } from 'src/utils/i18n'
import { mutate } from 'src/utils/zero-session'
import { client } from 'src/utils/hc'
import { computed, ref } from 'vue'
import { useQuasar } from 'quasar'
import ModelSelect from 'src/components/ModelSelect.vue'
import CommonItem from 'src/components/CommonItem.vue'

const workspaceStore = useWorkspaceStore()
const localEntitiesStore = useLocalEntitiesStore()
const $q = useQuasar()
const { conf, update: updateRootConf } = useRootEntityConf()
const { data: providerRows } = useQuery(() =>
  workspaceStore.id ? queries.recentProviders(workspaceStore.id) : null,
)
const { data: platformRows } = useQuery(queries.publicModels())
const { data: globalSettings } = useQuery(queries.globalSettings())

const providers = computed(() => providerRows.value ?? [])
const publicModels = computed(() => platformRows.value ?? [])
const kbPerfs = computed(() => (workspaceStore.workspace?.perfs ?? {}) as Record<string, unknown>)

const chatModelId = computed({
  get: () => conf.value.chatModelId,
  set: value => { updateRootConf('chatModelId', value) },
})
const embeddingModelId = computed({
  get: () => (typeof kbPerfs.value.embeddingModelId === 'string' ? kbPerfs.value.embeddingModelId : null),
  set: value => { setKb('embeddingModelId', value) },
})
const rerankModelId = computed({
  get: () => (typeof kbPerfs.value.rerankModelId === 'string' ? kbPerfs.value.rerankModelId : null),
  set: value => { setKb('rerankModelId', value) },
})
const searchMode = computed({
  get: () => parseKbSearchMode(kbPerfs.value.kbSearchMode),
  set: (value: KbSearchMode) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbSearchMode: value },
    }))
  },
})
const topK = computed({
  get: () => parseKbTopK(kbPerfs.value.kbTopK),
  set: (value: number) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbTopK: parseKbTopK(value) },
    }))
  },
})
const scoreThreshold = computed({
  get: () => parseKbScoreThreshold(kbPerfs.value.kbScoreThreshold),
  set: (value: number) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbScoreThreshold: parseKbScoreThreshold(value) },
    }))
  },
})
const vectorWeight = computed({
  get: () => parseKbVectorWeight(kbPerfs.value.kbVectorWeight),
  set: (value: number) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbVectorWeight: parseKbVectorWeight(value) },
    }))
  },
})
const chunkSize = computed({
  get: () => parseKbChunkSize(kbPerfs.value.kbChunkSize),
  set: (value: number) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbChunkSize: parseKbChunkSize(value) },
    }))
  },
})
const chunkOverlap = computed({
  get: () => parseKbChunkOverlap(kbPerfs.value.kbChunkOverlap),
  set: (value: number) => {
    if (!workspaceStore.id) return
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { kbChunkOverlap: parseKbChunkOverlap(value) },
    }))
  },
})

const reindexing = ref(false)
async function reindex() {
  if (!workspaceStore.id || reindexing.value) return
  reindexing.value = true
  try {
    const res = await client.api.kb.reindex.$post({
      json: { workspaceId: workspaceStore.id },
    })
    const data = await res.json() as { reindexed?: number }
    $q.notify({
      type: 'positive',
      message: t('Reindexed {0} files.', String(data.reindexed ?? 0)),
      timeout: 2500,
    })
  } catch {
    $q.notify({ type: 'negative', message: t('Reindex failed. Is the API server running?') })
  } finally {
    reindexing.value = false
  }
}

const searchModeOptions = [
  { label: t('Keyword'), value: 'keyword' },
  { label: t('Hybrid'), value: 'hybrid' },
  { label: t('Vector'), value: 'vector' },
]

const embeddingCaption = computed(() => {
  const fallback = globalSettings.value?.embeddingModelId
    ? t('Empty uses the platform default. Changing this does not re-index old files.')
    : t('Used when parsing files. Without it, Ask uses keyword search only. Changing this does not re-index old files.')
  return fallback
})

function setKb(key: string, value: string | null) {
  if (!workspaceStore.id) return
  if (value) {
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      updates: { [key]: value },
    }))
  } else {
    mutate(mutators.updateWorkspacePerfs({
      workspaceId: workspaceStore.id,
      deletes: [key],
    }))
  }
}

function addGateway() {
  const parentId = systemFolderId(
    localEntitiesStore.entities,
    workspaceStore.id!,
    '$providers',
  )
  createEntity(parentId, 'provider')
}
</script>
