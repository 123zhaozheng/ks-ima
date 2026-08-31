<template>
  <section
    class="tk-card settings-card"
    data-testid="settings-preferences"
  >
    <div class="settings-card-head">
      <h2 class="tk-card-title">
        {{ t('Preferences') }}
      </h2>
    </div>
    <q-list class="settings-list">
      <common-item
        icon="sym_o_language"
        :label="t('Language')"
      >
        <q-select
          v-model="localData.locale"
          filled
          dense
          :options="localeOptions"
          emit-value
          map-options
          class="w-120px"
        />
      </common-item>
      <common-item
        icon="sym_o_keyboard"
        :label="t('Send message')"
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
            {{ t('Model capabilities are centrally managed by a platform administrator.') }}
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
import { localData } from 'src/utils/local-data'
import { t } from 'src/utils/i18n'

const perfsStore = usePerfsStore()
const perfs = toRef(perfsStore, 'perfs')

function update<K extends keyof Perfs>(key: K, value: Perfs[K]) {
  perfsStore.update({
    updates: { [key]: value },
    scope: 'local',
  })
}

const localeOptions = [
  { label: t('Auto'), value: null },
  { label: 'English', value: 'en-US' },
  { label: '简体中文', value: 'zh-CN' },
  { label: '繁體中文', value: 'zh-TW' },
]
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
