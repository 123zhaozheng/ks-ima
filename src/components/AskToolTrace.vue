<template>
  <section
    v-if="calls.length"
    class="ask-tool-trace"
    data-testid="ask-tool-trace"
  >
    <button
      class="ask-tool-trace-toggle"
      type="button"
      :aria-expanded="expanded"
      aria-controls="ask-tool-trace-list"
      @click="expanded = !expanded"
    >
      <span class="ask-tool-trace-title">检索过程</span>
      <span class="ask-tool-trace-count">{{ calls.length }}</span>
      <span
        class="ask-tool-trace-chevron"
        aria-hidden="true"
      >{{ expanded ? '⌃' : '⌄' }}</span>
    </button>
    <div
      v-if="expanded"
      id="ask-tool-trace-list"
      class="ask-tool-trace-list"
    >
      <div
        v-for="(call, index) in calls"
        :key="`${call.round}-${call.name}-${index}`"
        class="ask-tool-trace-item"
      >
        <span class="ask-tool-trace-round">{{ call.round || index + 1 }}</span>
        <span class="ask-tool-trace-name">{{ toolLabel(call.name) }}</span>
        <span class="ask-tool-trace-summary">{{ argumentSummary(call.arguments) }}</span>
        <span class="ask-tool-trace-hits">{{ call.hitCount }} 条</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { AskToolCall } from 'src/composables/use-grounded-knowledge'

defineProps<{ calls: AskToolCall[] }>()
const expanded = ref(false)

function toolLabel(name: string): string {
  const labels: Record<string, string> = {
    search_knowledge: '检索知识',
    list_dir: '查看目录',
    get_document_outline: '查看大纲',
  }
  return labels[name] ?? name
}

function argumentSummary(argumentsValue: Record<string, unknown>): string {
  const values = Object.entries(argumentsValue)
    .slice(0, 2)
    .map(([key, value]) => `${key}: ${typeof value === 'string' ? value : String(value)}`)
  return values.join(' · ') || '已执行'
}
</script>

<style scoped>
.ask-tool-trace {
  border: 1px solid var(--tk-border);
  border-radius: var(--tk-radius);
  background-color: var(--tk-bg);
  color: var(--tk-text-secondary);
  margin-bottom: var(--tk-space-2);
}

.ask-tool-trace-toggle {
  align-items: center;
  background-color: transparent;
  border: 0;
  color: inherit;
  cursor: pointer;
  display: flex;
  font: inherit;
  gap: var(--tk-space-2);
  min-height: 36px;
  padding: var(--tk-space-2) var(--tk-space-3);
  text-align: left;
  width: 100%;
}

.ask-tool-trace-toggle:hover {
  background-color: var(--tk-surface);
}

.ask-tool-trace-title {
  color: var(--tk-text);
  font-size: 13px;
  font-weight: 500;
}

.ask-tool-trace-count {
  align-items: center;
  background-color: var(--tk-surface-deep);
  border-radius: var(--tk-radius-sm);
  display: inline-flex;
  font-size: 12px;
  justify-content: center;
  min-width: 20px;
  padding: 1px var(--tk-space-1);
}

.ask-tool-trace-chevron {
  margin-left: auto;
  color: var(--tk-text-tertiary);
  font-size: 16px;
}

.ask-tool-trace-list {
  border-top: 1px solid var(--tk-border);
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-1);
  padding: var(--tk-space-2) var(--tk-space-3);
}

.ask-tool-trace-item {
  align-items: center;
  display: flex;
  gap: var(--tk-space-2);
  min-height: 28px;
  min-width: 0;
  font-size: 12px;
}

.ask-tool-trace-round {
  color: var(--tk-text-tertiary);
  flex: 0 0 auto;
}

.ask-tool-trace-name {
  color: var(--tk-text);
  flex: 0 0 auto;
}

.ask-tool-trace-summary {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ask-tool-trace-hits {
  color: var(--tk-text-tertiary);
  flex: 0 0 auto;
  margin-left: auto;
}
</style>
