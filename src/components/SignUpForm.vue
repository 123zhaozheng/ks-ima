<template>
  <q-form @submit="signUp">
    <q-banner
      v-if="registration === false"
      rounded
      class="signup-notice"
      data-testid="sign-up-closed"
    >
      此服务器已关闭注册。请联系管理员获取邀请。
      <template #action>
        <q-btn
          flat
          dense
          no-caps
          color="primary"
          label="登录"
          @click="router.replace('/auth/sign-in')"
        />
      </template>
    </q-banner>
    <template v-else>
      <q-input
        label="名称"
        type="text"
        v-model="input.name"
        :rules="[
          val => val.length >= 2 || '名称至少 2 个字符'
        ]"
        filled
      />
      <q-input
        label="电子邮件"
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
        label="注册"
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
      message: apiErrorMessage(error, '注册失败'),
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
    $q.notify({ message: '账户已创建，现在可以登录了。', color: 'positive' })
    router.push('/auth/sign-in')
    return
  }
  $q.notify({ message: '账号已创建', color: 'positive' })
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
