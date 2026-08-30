<template>
  <q-list pb-2>
    <q-item-label header>
      {{ t('This device') }}
    </q-item-label>
    <common-item
      icon="sym_o_dark_mode"
      :label="t('Appearance')"
    >
      <q-select
        class="min-w-120px"
        filled
        dense
        :options="[
          { label: t('Follow System'), value: 'auto' },
          { label: t('Light'), value: false },
          { label: t('Dark'), value: true },
        ]"
        :model-value="perfs.darkMode"
        @update:model-value="update('darkMode', $event)"
        emit-value
        map-options
      />
    </common-item>
    <common-item
      icon="sym_o_palette"
      :label="t('Theme color')"
      clickable
      v-ripple
      @click="pickThemeHue"
    >
      <hct-preview-circle :hue="perfs.themeHue" />
    </common-item>
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
    <q-item text-on-sur-var>
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
import { useQuasar } from 'quasar'
import HueSliderDialog from './HueSliderDialog.vue'
import HctPreviewCircle from './HctPreviewCircle.vue'
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

const $q = useQuasar()
function pickThemeHue() {
  $q.dialog({
    component: HueSliderDialog,
    componentProps: { value: perfs.value.themeHue },
  }).onOk(hue => { update('themeHue', hue) })
}

const localeOptions = [
  { label: t('Auto'), value: null },
  { label: 'English', value: 'en-US' },
  { label: '简体中文', value: 'zh-CN' },
  { label: '繁體中文', value: 'zh-TW' },
]
</script>
