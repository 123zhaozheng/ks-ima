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
        v-if="registration"
        :label="t('Sign up')"
        to="/auth/sign-up"
        flat
        dense
        color="primary"
        data-testid="sign-up-link"
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
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'
import { onMounted, reactive, ref, watch } from 'vue'
import ForgotPasswordDialog from './ForgotPasswordDialog.vue'
import VerifyTotpDialog from './VerifyTotpDialog.vue'
import { useRoute, useRouter } from 'vue-router'

const input = reactive({
  email: '',
  password: '',
})

const loading = ref(false)
// Assume registration is open until the capabilities endpoint says otherwise,
// so a failed lookup never hides the sign-up path by mistake.
const registration = ref(true)
const $q = useQuasar()
const router = useRouter()
const route = useRoute()
function getRedirect() {
  return route.query.redirect as string || '/'
}

onMounted(async () => {
  const { data } = await identityClient.authCapabilities()
  if (data) registration.value = data.registration
})

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
      message: apiErrorMessage(result.error, 'Sign in failed'),
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
