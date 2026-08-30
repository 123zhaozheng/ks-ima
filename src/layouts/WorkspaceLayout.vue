<template>
  <!--
    Workspace admin pages now own their headers (the rail replaced the old
    tab bar). This layout only keeps the login + workspace guards.
  -->
  <router-view v-if="workspaceStore.id" />
</template>

<script setup lang="ts">
import { useWorkspaceStore } from 'src/stores/workspace'
import { useRequireLogin } from 'src/composables/require-login'

useRequireLogin()

const workspaceStore = useWorkspaceStore()
</script>
