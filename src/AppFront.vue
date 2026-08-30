<template>
  <app-shell />
</template>

<script setup lang="ts">
import { Dark } from 'quasar'
import AppShell from './layouts/AppShell.vue'
import { useRouter } from 'vue-router'
import { waitingWorker } from 'app/src-pwa/register-service-worker'

// Fixed light palette: tokens live in src/styles/tokens.css.
Dark.set(false)

const router = useRouter()
router.beforeEach((to, from) => {
  if (waitingWorker && to.path !== from.path) {
    navigator.serviceWorker.addEventListener('controllerchange', () => {
      location.href = to.fullPath
    }, { once: true })
    waitingWorker.postMessage({ type: 'SKIP_WAITING' })
    // Prevent hanging
    setTimeout(() => {
      location.href = to.fullPath
    }, 3000)
    return false
  }
})
</script>
