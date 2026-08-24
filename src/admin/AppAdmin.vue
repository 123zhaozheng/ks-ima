<template>
  <q-layout view="lHr Lpr lFf">
    <router-view />
  </q-layout>
</template>

<script setup lang="ts">
import { useSetTheme } from 'src/composables/set-theme'
import { watch } from 'vue'
import { DEFAULT_HUE } from 'src/utils/config'
import { session } from 'src/utils/identity-client'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'

useSetTheme(DEFAULT_HUE)

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
      message: t('You need to be an admin to access this page'),
      color: 'negative',
    })
    router.replace('/auth/sign-in')
  }
}, { immediate: true })
</script>
