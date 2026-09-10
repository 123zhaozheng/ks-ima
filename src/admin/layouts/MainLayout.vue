<template>
  <q-layout view="lHr Lpr lFf">
    <admin-drawer v-model="drawerOpen" />
    <q-header
      bg-sur-c-low
      text-on-sur
    >
      <q-toolbar>
        <q-btn
          flat
          dense
          round
          icon="sym_o_menu"
          @click="drawerOpen = !drawerOpen"
        />
        <q-toolbar-title>{{ $route.meta.title }}</q-toolbar-title>
        <system-status-indicator />
      </q-toolbar>
    </q-header>
    <router-view />
  </q-layout>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AdminDrawer from '../components/AdminDrawer.vue'
import SystemStatusIndicator from '../components/SystemStatusIndicator.vue'

const drawerOpen = ref(false)
</script>
