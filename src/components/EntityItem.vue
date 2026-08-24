<template>
  <q-item
    item-rd
    min-h="40px"
    py-0
    px-3
    border="pri 2px"
    :class="{ 'border-solid': selected }"
    class="group"
  >
    <q-item-section
      avatar
      min-w-0
      pr-3
    >
      <a-avatar
        :avatar="entityAvatar(entity)"
        size="27px"
      />
    </q-item-section>
    <q-item-section>
      <q-item-label
        text-ellipsis
        whitespace-nowrap
        overflow-hidden
        :title="entityName(entity)"
      >
        {{ entityName(entity) }}
      </q-item-label>
      <q-item-label
        v-if="parseLabel"
        caption
        :class="parseClass"
        :title="parseError"
      >
        {{ parseLabel }}
      </q-item-label>
    </q-item-section>
    <q-item-section
      side
      important:pl-2
    >
      <q-icon
        v-if="selectable"
        :name="selected ? 'sym_o_check_circle' : 'sym_o_circle'"
        :class="selected ? 'text-pri icon-fill' : 'text-on-sur-var icon-unfill'"
      />
      <slot
        v-else
        name="actions"
      />
    </q-item-section>
  </q-item>
</template>

<script setup lang="ts">
import type { FullEntity } from 'app/src-shared/queries'
import { computed } from 'vue'
import AAvatar from './AAvatar.vue'
import { entityAvatar, entityName } from 'src/utils/defaults'
import { itemParseStatus } from 'src/utils/knowledge'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  entity: FullEntity
  selectable?: boolean
  selected?: boolean
}>()

const parseStatus = computed(() => props.entity.type === 'item' ? itemParseStatus(props.entity.item, props.entity.conf) : null)
const parseError = computed(() => typeof props.entity.conf?.parseError === 'string' ? props.entity.conf.parseError : '')
const parseLabel = computed(() => {
  if (parseStatus.value === 'ready') {
    return props.entity.conf?.indexed === true
      ? t('Parsed · Vector indexed')
      : t('Parsed · Keyword only')
  }
  if (parseStatus.value === 'parsing') return t('Parsing…')
  if (parseStatus.value === 'unparsed') return t('No text extracted')
  if (parseStatus.value === 'failed') return t('Parse failed')
  return ''
})
const parseClass = computed(() => {
  if (parseStatus.value === 'ready') return 'text-pri'
  if (parseStatus.value === 'unparsed' || parseStatus.value === 'failed') return 'text-warn'
  return 'text-on-sur-var'
})
</script>
