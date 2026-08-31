<template>
  <q-layout view="lHr Lpr lFf">
    <router-view />
  </q-layout>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import { session } from 'src/utils/identity-client'
import { useRouter } from 'vue-router'
import { Dark, useQuasar } from 'quasar'

// Fixed light palette: tokens live in src/styles/tokens.css.
Dark.set(false)

const router = useRouter()
const $q = useQuasar()
watch(() => [session.value.isPending, session.value.data?.user.id] as const, () => {
  const { data, isPending } = session.value
  if (isPending) return
  if (!data) {
    router.replace('/auth/sign-in')
    return
  }
  if (!data.user.platformRoles?.some(role => role === 'super_admin' || role === 'platform_admin' || role === 'security_auditor')) {
    $q.notify({
      message: '您需要成为管理员才能访问此页面',
      color: 'negative',
    })
    router.replace('/auth/sign-in')
  }
}, { immediate: true })
</script>
