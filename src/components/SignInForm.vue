<template>
  <q-form
    class="auth-form"
    @submit="signIn"
  >
    <q-input
      v-model="input.email"
      label="电子邮件"
      type="email"
      required
      outlined
      autocomplete="email"
    >
      <template #prepend>
        <q-icon
          name="sym_o_mail"
          size="20px"
        />
      </template>
    </q-input>
    <q-input
      v-model="input.password"
      label="密码"
      :type="showPassword ? 'text' : 'password'"
      required
      outlined
      autocomplete="current-password"
      class="auth-field"
    >
      <template #prepend>
        <q-icon
          name="sym_o_lock"
          size="20px"
        />
      </template>
      <template #append>
        <q-icon
          :name="showPassword ? 'sym_o_visibility_off' : 'sym_o_visibility'"
          class="auth-pw-toggle"
          size="20px"
          role="button"
          :aria-label="showPassword ? '隐藏密码' : '显示密码'"
          @click="showPassword = !showPassword"
        />
      </template>
    </q-input>
    <q-btn
      label="登录"
      :loading
      type="submit"
      unelevated
      no-caps
      color="primary"
      class="auth-submit"
    />
    <div class="auth-links">
      <q-btn
        v-if="registration"
        label="注册"
        to="/auth/sign-up"
        flat
        dense
        no-caps
        color="primary"
        data-testid="sign-up-link"
      />
      <q-btn
        label="忘记密码"
        flat
        dense
        no-caps
        color="primary"
        class="auth-links-right"
        @click="forgotPassword"
      />
    </div>
  </q-form>
</template>

<script setup lang="ts">

import { useQuasar } from 'quasar'
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
const showPassword = ref(false)
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
      message: apiErrorMessage(result.error, '登录失败'),
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

<style scoped>
.auth-field {
  margin-top: var(--tk-space-4);
}

.auth-pw-toggle {
  cursor: pointer;
  color: var(--tk-text-tertiary);
}

.auth-pw-toggle:hover {
  color: var(--tk-text-secondary);
}

.auth-submit {
  width: 100%;
  min-height: 40px;
  margin-top: var(--tk-space-6);
  border-radius: var(--tk-radius);
  font-size: var(--tk-font-size-sm);
}

.auth-links {
  display: flex;
  align-items: center;
  margin-top: var(--tk-space-3);
}

.auth-links-right {
  margin-left: auto;
}
</style>
