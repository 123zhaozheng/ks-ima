<template>
  <q-form @submit="submit">
    <q-input
      v-model="displayName"
      label="显示名称"
      required
      filled
    />
    <q-input
      v-model="password"
      label="密码"
      type="password"
      required
      filled
      class="mt-4"
    />
    <q-btn
      label="接受邀请"
      :loading="loading"
      type="submit"
      unelevated
      color="primary"
      mt-4
      w-full
    />
  </q-form>
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar'
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { identityClient } from 'src/utils/identity-client'

const route = useRoute()
const router = useRouter()
const $q = useQuasar()
const displayName = ref('')
const password = ref('')
const loading = ref(false)

async function submit() {
  const token = String(route.query.token ?? '')
  loading.value = true
  const result = await identityClient.acceptInvite({ token, password: password.value, displayName: displayName.value })
  loading.value = false
  if (result.error) {
    $q.notify({ message: result.error.message, color: 'negative' })
    return
  }
  $q.notify({ message: '已接受邀请，请登录。', color: 'positive' })
  await router.replace('/auth/sign-in')
}
</script>
