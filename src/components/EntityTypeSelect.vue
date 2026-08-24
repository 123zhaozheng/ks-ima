<template>
  <q-select
    v-model="model"
    :options
    map-options
    emit-value
  />
</template>

<script setup lang="ts">
import type { EntityType } from 'app/src-shared/utils/validators'
import { t } from 'src/utils/i18n'

const model = defineModel<EntityType | null>()

const options = [
  { label: t('All'), value: null },
  { label: t('Folder'), value: 'folder' },
  { label: t('File'), value: 'item' },
]
</script>
