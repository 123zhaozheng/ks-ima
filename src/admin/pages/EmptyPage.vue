<template>
  <div />
</template>
<script setup lang="ts">
import { session } from 'src/utils/identity-client'
import { useRouter } from 'vue-router'
import { watch } from 'vue'

const router = useRouter()
watch(() => [session.value.isPending, session.value.data?.user.id] as const, ([isPending, id]) => {
  if (isPending) return
  router.replace(id ? '/admin/users' : '/auth/sign-in')
}, { immediate: true })
</script>
