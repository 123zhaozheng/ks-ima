<template>
  <q-form @submit="signUp">
    <q-banner
      v-if="registration === false"
      rounded
      class="signup-notice"
      data-testid="sign-up-closed"
    >
      {{ t('Registration is closed on this server. Ask an administrator for an invitation.') }}
      <template #action>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          :label="t('Sign In')"
          @click="router.replace('/auth/sign-in')"
        />
      </template>
    </q-banner>
    <template v-else>
      <q-input
        :label="t('Name')"
        type="text"
        v-model="input.name"
        :rules="[
          val => val.length >= 2 || t('Name must be at least 2 characters long')
        ]"
        filled
      />
      <q-input
        :label="t('Email')"
        type="email"
        v-model="input.email"
        required
        filled
        class="mt-2"
      />
      <set-password-inputs
        v-model="input.password"
        mt-6
        filled
      />
      <q-btn
        :label="t('Sign Up')"
        :loading
        type="submit"
        unelevated
        color="primary"
        mt-4
        w-full
        h="40px"
        data-testid="sign-up-button"
      />
    </template>
  </q-form>
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'
import { onMounted, reactive, ref, watch } from 'vue'
import SetPasswordInputs from './SetPasswordInputs.vue'
import VerifyTotpDialog from './VerifyTotpDialog.vue'
import { useRoute, useRouter } from 'vue-router'

const input = reactive({
  name: '',
  email: '',
  password: '',
})

const loading = ref(false)
// undefined while the capabilities lookup is in flight; never hide the form
// before we know registration is actually closed.
const registration = ref<boolean>()
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

async function signUp() {
  loading.value = true
  const { error } = await identityClient.register({
    displayName: input.name,
    email: input.email,
    password: input.password,
  })
  if (error) {
    loading.value = false
    console.error(error)
    $q.notify({
      message: apiErrorMessage(error, 'Sign up failed'),
      color: 'negative',
    })
    return
  }
  // Sign the fresh account in immediately so first run flows straight into
  // the app instead of bouncing through the sign-in page.
  const signed = await identityClient.signIn({
    email: input.email,
    password: input.password,
  })
  loading.value = false
  if (signed.data?.status === 'totp_required' && signed.data.challenge) {
    $q.dialog({
      component: VerifyTotpDialog,
      componentProps: {
        challenge: signed.data.challenge,
      },
      persistent: true,
    })
    router.push('/auth/sign-in')
    return
  }
  if (signed.error || !signed.data?.user) {
    $q.notify({ message: t('Account created. You can now sign in.'), color: 'positive' })
    router.push('/auth/sign-in')
    return
  }
  $q.notify({ message: t('Account created'), color: 'positive' })
}

watch(() => session.value.data?.user.id, id => {
  if (id) router.replace(getRedirect())
}, { immediate: true })
</script>

<style scoped>
.signup-notice {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}
</style>
