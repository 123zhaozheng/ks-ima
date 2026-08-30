<template>
  <div>
    <q-form @submit="signIn">
      <q-input
        :label="t('Email')"
        type="email"
        v-model="input.email"
        required
        filled
      />
      <q-input
        :label="t('Password')"
        type="password"
        v-model="input.password"
        required
        filled
        class="mt-4"
      />
      <q-btn
        :label="t('Sign In')"
        :loading
        type="submit"
        unelevated
        color="primary"
        mt-4
        w-full
        h="40px"
      />
    </q-form>
    <div
      mt-2
      flex
    >
      <q-btn
        :label="t('Sign up')"
        to="/auth/sign-up"
        flat
        dense
        color="primary"
      />
      <q-btn
        :label="t('Forgot password')"
        flat
        dense
        color="primary"
        ml-a
        @click="forgotPassword"
      />
    </div>
  </div>
</template>

<script setup lang="ts">

import { useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { identityClient, session } from 'src/utils/identity-client'
import { reactive, ref, watch } from 'vue'
import ForgotPasswordDialog from './ForgotPasswordDialog.vue'
import VerifyTotpDialog from './VerifyTotpDialog.vue'
import { useRoute, useRouter } from 'vue-router'

const input = reactive({
  email: '',
  password: '',
})

const loading = ref(false)
const $q = useQuasar()
const router = useRouter()
const route = useRoute()
function getRedirect() {
  return route.query.redirect as string || '/'
}
async function signIn() {
  loading.value = true
  const result = await identityClient.signIn({
    email: input.email,
    password: input.password,
  })
  loading.value = false
  if (result.data?.status === 'totp_required' && result.data.challenge) {
    $q.dialog({
      component: VerifyTotpDialog,
      componentProps: {
        challenge: result.data.challenge,
      },
      persistent: true,
    })
  } else if (result.error) {
    console.error(result.error)
    $q.notify({
      message: t('Failed to sign in: {0}', result.error.message),
      color: 'negative',
    })
  }
}

function forgotPassword() {
  $q.dialog({
    component: ForgotPasswordDialog,
  })
}

watch(session, s => {
  if (s.isPending || s.error) return
  if (s.data?.user.id) router.replace(getRedirect())
}, { immediate: true })
</script>
