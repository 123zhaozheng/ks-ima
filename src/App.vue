<template>
  <router-view />
</template>
<script lang="ts" setup>
import { Dark } from 'quasar'
import { useRouter } from 'vue-router'

// Fixed light palette: tokens live in src/styles/tokens.css.
Dark.set(false)

const router = useRouter()
router.afterEach(to => {
  if (to.meta.title) {
    document.title = `${to.meta.title as string} - Nya AI`
  }
})
</script>
