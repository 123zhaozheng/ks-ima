<template>
  <q-page class="q-pa-md">
    <div class="row q-col-gutter-md">
      <section class="col-12 col-md-6">
        <q-input
          v-model="query"
          outlined
          label="Search knowledge"
          :loading="searching"
          @keyup.enter="runSearch"
        >
          <template #append>
            <q-btn flat round icon="sym_o_search" aria-label="Search knowledge" @click="runSearch" />
          </template>
        </q-input>
        <q-banner v-if="searchError" class="q-mt-sm bg-negative text-white">{{ searchError }}</q-banner>
        <q-list v-if="results.length" bordered separator class="q-mt-md">
          <q-item v-for="result in results" :key="`${result.documentId}-${result.chunkOrdinal}`" clickable :to="`/knowledge/${result.documentId}`">
            <q-item-section>
              <q-item-label>{{ result.title }}</q-item-label>
              <q-item-label caption lines="3">{{ result.quote }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
        <q-banner v-else-if="searched && !searching" class="q-mt-md">No accessible knowledge matched this search.</q-banner>
      </section>
      <section class="col-12 col-md-6">
        <q-input
          v-model="question"
          outlined
          type="textarea"
          autogrow
          label="Ask grounded knowledge"
          :disable="status === 'streaming'"
          @keyup.ctrl.enter="submitAsk"
        />
        <div class="row q-gutter-sm q-mt-sm">
          <q-btn color="primary" icon="sym_o_send" label="Ask" :loading="status === 'streaming'" @click="submitAsk" />
          <q-btn v-if="status === 'streaming'" flat icon="sym_o_stop_circle" aria-label="Cancel Ask" @click="cancel" />
        </div>
        <q-banner v-if="status === 'knowledge_gap'" class="q-mt-md">No relevant accessible source was found.</q-banner>
        <q-banner v-if="status === 'failed'" class="q-mt-md bg-negative text-white">Grounded Ask is unavailable. Sources were not broadened.</q-banner>
        <q-banner v-if="status === 'cancelled'" class="q-mt-md">Ask was cancelled.</q-banner>
        <div v-if="answer" class="q-mt-md whitespace-pre-wrap">{{ answer }}</div>
        <q-list v-if="citations.length" bordered separator class="q-mt-md">
          <q-item v-for="citation in citations" :key="`${citation.documentId}-${citation.chunkOrdinal}`" clickable :to="`/knowledge/${citation.documentId}`">
            <q-item-section>
              <q-item-label>Source {{ citation.rank }}</q-item-label>
              <q-item-label caption lines="2">{{ citation.quote }}</q-item-label>
            </q-item-section>
          </q-item>
        </q-list>
      </section>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { groundedClient } from 'src/api/grounded-client'
import { useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useWorkspaceStore } from 'src/stores/workspace'

const workspace = useWorkspaceStore()
const query = ref('')
const results = ref<Array<Record<string, unknown>>>([])
const searched = ref(false)
const searching = ref(false)
const searchError = ref('')
const question = ref('')
const { answer, ask, cancel, citations, status } = useGroundedKnowledge(() => workspace.id)

async function runSearch() {
  if (!workspace.id || !query.value.trim()) return
  searching.value = true
  searchError.value = ''
  searched.value = true
  try {
    results.value = (await groundedClient.search(workspace.id, query.value)).items as Array<Record<string, unknown>>
  } catch {
    results.value = []
    searchError.value = 'Search is unavailable.'
  } finally {
    searching.value = false
  }
}

async function submitAsk() {
  if (!question.value.trim()) return
  try {
    await ask(question.value)
  } catch {
    // The composable records the stable visible failure state.
  }
}
</script>
