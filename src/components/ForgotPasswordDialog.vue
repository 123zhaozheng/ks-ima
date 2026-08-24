<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Forgot Password') }}
        </div>
      </q-card-section>
      <q-card-section py-0>
        {{ t('Please enter your email. We will send you a link to reset your password.') }}
      </q-card-section>
      <q-form @submit="send">
        <q-card-section py-2>
          <q-input
            v-model="email"
            :label="t('Email')"
            type="email"
            required
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
            :label="t('Send')"
            :loading
            type="submit"
          />
        </q-card-actions>
      </q-form>
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

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const email = ref('')

const $q = useQuasar()
const loading = ref(false)
async function send() {
  loading.value = true

  const { error } = await identityClient.requestPasswordReset({
    email: email.value,
  })
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      message: t('Failed to request password reset: {0}', error.message),
      color: 'negative',
    })
    return
  }
  $q.notify(t('Password reset email sent'))
  onDialogOK()
}
</script>
