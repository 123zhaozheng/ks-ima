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
      label="重置密码"
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
    令牌无效或过期
  </div>
</template>

<script setup lang="ts">
import { identityClient } from 'src/utils/identity-client'
import SetPasswordInputs from './SetPasswordInputs.vue'
import { useRoute, useRouter } from 'vue-router'
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
      message: `重置密码失败：${error.message}`,
      color: 'negative',
    })
    return
  }
  $q.notify({
    message: '密码重置成功',
    color: 'positive',
  })
  router.push('/auth/sign-in')
}
</script>
