<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Change Password') }}
        </div>
      </q-card-section>
      <q-form @submit="update">
        <q-card-section py-0>
          <q-input
            v-model="password.old"
            :label="t('Old Password')"
            type="password"
          />
          <set-password-inputs v-model="password.new" />
          <q-checkbox
            v-model="revokeOtherSessions"
            :label="t('Revoke other sessions')"
            dense
          />
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
            type="submit"
            :loading
          />
        </q-card-actions>
      </q-form>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { reactive, ref } from 'vue'
import SetPasswordInputs from './SetPasswordInputs.vue'
import { identityClient } from 'src/utils/identity-client'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const password = reactive({
  old: '',
  new: '',
})

const revokeOtherSessions = ref(false)

const loading = ref(false)
const $q = useQuasar()
async function update() {
  loading.value = true
  const { error } = await identityClient.changePassword({
    currentPassword: password.old,
    password: password.new,
  })
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      type: 'negative',
      message: t('Failed to change password: {0}', error.message),
    })
    return
  }
  $q.notify({
    type: 'positive',
    message: t('Password updated successfully'),
  })
  onDialogOK()
}
</script>
