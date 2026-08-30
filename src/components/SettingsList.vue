<template>
  <q-list class="settings-list">
    <q-item-label header>
      {{ t('This device') }}
    </q-item-label>
    <common-item
      icon="sym_o_language"
      :label="t('Language')"
    >
      <q-select
        filled
        dense
        :options="localeOptions"
        v-model="localData.locale"
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
        @update:model-value="v => { if (v) update('sendMessageKey', v) }"
        dense
        filled
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
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import type { Perfs } from 'src/stores/perfs'
import { usePerfsStore } from 'src/stores/perfs'
import SendKeySelect from './SendKeySelect.vue'
import CommonItem from './CommonItem.vue'
import { localData } from 'src/utils/local-data'
import { toRef } from 'vue'

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
.settings-list {
  padding-bottom: var(--tk-space-2);
}
</style>
