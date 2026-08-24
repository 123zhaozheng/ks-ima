<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('List Options') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <q-item>
            <q-item-section>
              {{ t('Sort') }}
            </q-item-section>
            <q-item-section side>
              <q-select
                v-model="model.orderBy"
                :options="sortOptions"
                map-options
                emit-value
                dense
              />
            </q-item-section>
          </q-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          :label="t('Cancel')"
          @click="onDialogCancel"
        />
        <q-btn
          flat
          color="primary"
          :label="t('OK')"
          @click="onDialogOK(model)"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent } from 'quasar'
import { reactive } from 'vue'
import { t } from 'src/utils/i18n'
import type { EntityListOptions } from 'app/src-shared/utils/validators'

const props = defineProps<{
  value: EntityListOptions
}>()

const model = reactive({ ...props.value })

const sortOptions = [
  { label: t('Latest Created'), value: ['id', 'desc'] },
  { label: t('Earliest Created'), value: ['id', 'asc'] },
  { label: t('Name Ascending'), value: ['name', 'asc'] },
  { label: t('Name Descending'), value: ['name', 'desc'] },
] as const

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
</script>
