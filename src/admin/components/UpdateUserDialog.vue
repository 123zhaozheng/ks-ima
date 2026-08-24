<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Edit User') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item :label="t('Name')">
            <q-input
              v-model="model.name"
              dense
            />
          </common-item>
          <common-item :label="t('Email')">
            <q-input
              v-model="model.email"
              type="email"
              dense
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
          :label="t('Update')"
          @click="updateUser"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { reactive, ref } from 'vue'
import CommonItem from '../../components/CommonItem.vue'
import { identityClient } from 'src/utils/identity-client'

type UserWithRole = { id: string, displayName: string, email: string }

defineEmits([
  ...useDialogPluginComponent.emits,
])

const props = defineProps<{
  user: UserWithRole
}>()

const model = reactive({ name: props.user.displayName, email: props.user.email })

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const $q = useQuasar()
async function updateUser() {
  loading.value = true
  const result = await identityClient.updateUser(props.user.id, { displayName: model.name, email: model.email })
  if (!result.error) {
    onDialogOK()
  } else {
    $q.notify({
      message: t('Failed to update user: {0}', result.error.message),
      color: 'negative',
    })
  }
  loading.value = false
}
</script>
