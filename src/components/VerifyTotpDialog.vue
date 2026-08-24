<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Two-Factor Authentication') }}
        </div>
      </q-card-section>
      <q-card-section py-0>
        {{ recoveryMode ? t('Enter one unused recovery code.') : t('Please enter the TOTP code from your authenticator app.') }}
      </q-card-section>
      <q-card-section py-2>
        <q-input
          v-model="totp"
          :label="recoveryMode ? t('Recovery code') : t('TOTP code')"
          :type="recoveryMode ? 'text' : 'number'"
        />
      </q-card-section>
      <q-card-actions>
        <q-btn
          flat
          color="primary"
          :label="recoveryMode ? t('Use authenticator code') : t('Use recovery code')"
          @click="useBackupCode"
        />
        <q-space />
        <q-btn
          flat
          color="primary"
          :label="t('Verify')"
          :loading
          @click="verify"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import { ref } from 'vue'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()
const props = defineProps<{ challenge: string }>()

const totp = ref('')
const recoveryMode = ref(false)

const $q = useQuasar()
const loading = ref(false)
async function verify() {
  loading.value = true

  const result = recoveryMode.value
    ? await identityClient.verifyRecovery({ code: totp.value, challenge: props.challenge })
    : await identityClient.verifyTotp({ code: totp.value, challenge: props.challenge })
  const { error } = result
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      message: t('Verification failed: {0}', error.message),
      color: 'negative',
    })
    return
  }
  onDialogOK()
}

function useBackupCode() { recoveryMode.value = !recoveryMode.value; totp.value = '' }
</script>
