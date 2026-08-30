<template>
  <q-page-container>
    <q-page
      class="auth-page"
      flex="~ col"
      flex-center
    >
      <div class="tk-card auth-card">
        <div
          v-if="$route.meta.title"
          class="auth-title"
        >
          {{ $route.meta.title }}
        </div>
        <router-view />
      </div>
    </q-page>
  </q-page-container>
</template>

<style scoped>
.auth-page {
  padding: var(--tk-space-4);
}

.auth-card {
  width: min(92vw, 420px);
  padding: var(--tk-space-8) var(--tk-space-6);
}

.auth-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--tk-text);
  margin-bottom: var(--tk-space-6);
}
</style>
