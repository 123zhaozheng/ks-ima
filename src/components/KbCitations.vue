<template>
  <div
    v-if="citations.length"
    flex="~ wrap"
    gap-1
    mt-2
  >
    <q-chip
      v-for="(c, i) in citations"
      :key="c.entityId + i"
      clickable
      dense
      outline
      color="primary"
      :to="`/item/${c.entityId}`"
      :title="c.quote"
    >
      {{ i + 1 }}. {{ c.title || c.path || c.entityId }}
    </q-chip>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Row } from '@rocicorp/zero'

const props = defineProps<{
  toolCall: Row['toolCall']
}>()

type Citation = {
  entityId: string
  title?: string | null
  path?: string | null
  quote?: string
}

const citations = computed(() => parseCitations(props.toolCall))

function parseCitations(toolCall: Row['toolCall']): Citation[] {
  if (toolCall.pluginId !== 'workspace' || toolCall.name !== 'search') return []
  const items = toolCall.result
  if (!Array.isArray(items)) return []
  const text = items.find(item => item && typeof item === 'object' && 'text' in item)?.text
  if (typeof text !== 'string') return []
  try {
    const parsed = JSON.parse(text) as unknown
    const batches = Array.isArray(parsed) ? parsed : [parsed]
    const out: Citation[] = []
    const seen = new Set<string>()
    for (const batch of batches) {
      const rows = Array.isArray(batch)
        ? batch
        : Array.isArray((batch as { results?: unknown }).results)
          ? (batch as { results: unknown[] }).results
          : []
      for (const row of rows) {
        if (!row || typeof row !== 'object' || !('entityId' in row)) continue
        const c = row as Citation
        if (seen.has(c.entityId)) continue
        seen.add(c.entityId)
        out.push(c)
      }
    }
    return out
  } catch {
    return []
  }
}
</script>
