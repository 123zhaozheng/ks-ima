<template>
  <div class="cv-sources">
    <div class="cv-sources-title">
      {{ t('Sources') }}
    </div>
    <button
      v-for="citation in citations"
      :key="citation.rank"
      type="button"
      class="cv-source"
      data-testid="citation-source"
      @click="emit('open', citation)"
    >
      <span class="cv-source-rank">{{ citation.rank }}</span>
      <span class="cv-source-quote">{{ citation.quote }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { t } from 'src/utils/i18n'

type Citation = components['schemas']['CitationResponse'] & { title?: string }

defineProps<{
  citations: Citation[]
}>()

const emit = defineEmits<{
  open: [citation: Citation]
}>()
</script>

<style scoped>
.cv-sources {
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-1);
  margin-top: var(--tk-space-2);
}

.cv-sources-title {
  font-size: 12px;
  color: var(--tk-text-tertiary);
  margin-bottom: var(--tk-space-1);
}

.cv-source {
  display: flex;
  align-items: flex-start;
  gap: var(--tk-space-2);
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-bg);
  color: var(--tk-text-secondary);
  font-size: 13px;
  line-height: 1.5;
  text-align: left;
  padding: var(--tk-space-1) var(--tk-space-2);
  cursor: pointer;
}

.cv-source:hover {
  border-color: var(--tk-accent);
  color: var(--tk-text);
}

.cv-source-rank {
  flex: 0 0 auto;
  min-width: 18px;
  height: 18px;
  border-radius: var(--tk-radius-sm);
  background-color: var(--tk-accent-soft);
  color: var(--tk-accent);
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.cv-source-quote {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}
</style>
