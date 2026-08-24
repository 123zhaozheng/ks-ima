<template>
  <q-form
    v-if="$route.query.token"
    @submit="resetPassword"
  >
    <set-password-inputs
      v-model="password"
      filled
    />
    <q-btn
      :label="t('Reset Password')"
      :loading
      type="submit"
      unelevated
      color="primary"
      mt-4
      w-full
    />
  </q-form>
  <div
    v-else
    text="err center xl"
  >
    {{ t('Invalid or expired token') }}
  </div>
</template>

<script setup lang="ts">
import { identityClient } from 'src/utils/identity-client'
import SetPasswordInputs from './SetPasswordInputs.vue'
import { useRoute, useRouter } from 'vue-router'
import { t } from 'src/utils/i18n'
import { useQuasar } from 'quasar'
import { ref } from 'vue'

const password = ref('')

const $q = useQuasar()
const route = useRoute()
const router = useRouter()
const loading = ref(false)
async function resetPassword() {
  loading.value = true
  const { error } = await identityClient.resetPassword({
    password: password.value,
    token: route.query.token as string,
  })
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      message: t('Failed to reset password: {0}', error.message),
      color: 'negative',
    })
    return
  }
  $q.notify({
    message: t('Password reset successfully'),
    color: 'positive',
  })
  router.push('/auth/sign-in')
}
</script>
