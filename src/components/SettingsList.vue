<template>
  <section
    class="tk-card settings-card"
    data-testid="settings-preferences"
  >
    <div class="settings-card-head">
      <h2 class="tk-card-title">
        偏好
      </h2>
    </div>
    <q-list class="settings-list">
      <common-item
        icon="sym_o_keyboard"
        label="发送消息"
      >
        <send-key-select
          :model-value="perfs.sendMessageKey"
          dense
          filled
          @update:model-value="v => { if (v) update('sendMessageKey', v) }"
        />
      </common-item>
      <q-item>
        <q-item-section>
          <q-item-label caption>
            模型能力由平台管理员集中管理。
          </q-item-label>
        </q-item-section>
      </q-item>
    </q-list>
  </section>
</template>

<script setup lang="ts">
import { toRef } from 'vue'
import type { Perfs } from 'src/stores/perfs'
import { usePerfsStore } from 'src/stores/perfs'
import SendKeySelect from './SendKeySelect.vue'
import CommonItem from './CommonItem.vue'

const perfsStore = usePerfsStore()
const perfs = toRef(perfsStore, 'perfs')

function update<K extends keyof Perfs>(key: K, value: Perfs[K]) {
  perfsStore.update({
    updates: { [key]: value },
    scope: 'local',
  })
}
</script>

<style scoped>
.settings-card-head {
  display: flex;
  align-items: center;
  gap: var(--tk-space-3);
  padding: var(--tk-space-4) var(--tk-space-4) var(--tk-space-2);
}

.settings-list {
  padding-bottom: var(--tk-space-2);
}
</style>
