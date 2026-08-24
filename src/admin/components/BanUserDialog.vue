<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Ban User') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item :label="t('Ban Reason')">
            <q-input
              v-model="reason"
              dense
              field-sizing-content
              min-w="120px"
            />
          </common-item>
          <common-item :label="t('Ban Period')">
            <q-input
              v-model.number="periodDays"
              type="number"
              :placeholder="t('Forever')"
              :suffix="t('Days')"
              dense
              class="w-120px"
            />
          </common-item>
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
          :label="t('Ban')"
          @click="banUser"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { ref } from 'vue'
import CommonItem from '../../components/CommonItem.vue'
import { identityClient } from 'src/utils/identity-client'

type UserWithRole = { id: string, displayName: string, email: string, isActive: boolean }

defineEmits([
  ...useDialogPluginComponent.emits,
])

const props = defineProps<{
  user: UserWithRole
}>()

const reason = ref('')
const periodDays = ref<number | null>(null)

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const $q = useQuasar()
async function banUser() {
  loading.value = true
  const result = await identityClient.disableUser(props.user.id)
  if (!result.error) {
    onDialogOK()
  } else {
    $q.notify({
      message: t('Failed to ban user: {0}', result.error.message),
      color: 'negative',
    })
  }
  loading.value = false
}
</script>
