<template>
  <q-page-container>
    <q-page
      class="invite-page"
      flex="~ col"
      flex-center
    >
      <div class="tk-card invite-card">
        <q-icon
          name="sym_o_mail"
          size="48px"
          color="primary"
        />
        <div class="invite-title">
          {{ t('Join workspace') }}
        </div>
        <div class="invite-subtitle">
          {{ t('Accept the invitation to become a member of this workspace.') }}
        </div>
        <div
          v-if="error"
          class="invite-error"
          aria-live="polite"
        >
          {{ error }}
        </div>
        <q-btn
          color="primary"
          :label="t('Join workspace')"
          :loading="loading"
          unelevated
          no-caps
          class="w-full"
          @click="join"
        />
      </div>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useQuasar } from 'quasar'
import { useRequireLogin } from 'src/composables/require-login'
import { useWorkspaceStore } from 'src/stores/workspace'
import { identityClient } from 'src/utils/identity-client'
import { queryClient } from 'src/boot/vue-query'
import { t } from 'src/utils/i18n'

useRequireLogin()

const props = defineProps<{
  token: string
}>()

const loading = ref(false)
const error = ref('')
const $q = useQuasar()
const workspaceStore = useWorkspaceStore()
const router = useRouter()

async function join() {
  loading.value = true
  error.value = ''
  try {
    const result = await identityClient.acceptWorkspaceInvitation(props.token)
    if (!result.data) {
      const message = result.error?.message ?? t('Failed to join workspace')
      error.value = message
      throw new Error(message)
    }
    await queryClient.invalidateQueries({ queryKey: ['workspaces', 'member'] })
    workspaceStore.switchWorkspace(result.data.workspaceId)
    router.push('/')
  } catch (err) {
    console.error(err)
    $q.notify({
      message: t('Failed to join workspace: {0}', err instanceof Error ? err.message : String(err)),
      color: 'negative',
    })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.invite-page {
  padding: var(--tk-space-4);
}

.invite-card {
  width: min(92vw, 420px);
  padding: var(--tk-space-8) var(--tk-space-6);
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: var(--tk-space-3);
}

.invite-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--tk-text);
}

.invite-subtitle {
  font-size: 13px;
  color: var(--tk-text-secondary);
  margin-bottom: var(--tk-space-2);
}

.invite-error {
  font-size: 13px;
  color: var(--tk-danger);
}
</style>
