<template>
  <q-page-container>
    <q-page
      flex="~ col"
      justify-center
      items-center
    >
      <div
        text-center
        px-6
        style="width: min(92vw, 420px)"
      >
        <q-icon
          name="sym_o_mail"
          size="56px"
        />
        <div
          text="center xl"
          mt-3
        >
          {{ t('Join workspace') }}
        </div>
        <div
          text-on-sur-var
          text-caption
          mt-2
        >
          {{ t('Accept the invitation to become a member of this workspace.') }}
        </div>
        <div
          v-if="error"
          text-err
          text-caption
          mt-3
          aria-live="polite"
        >
          {{ error }}
        </div>
        <q-btn
          color="primary"
          :label="t('Join workspace')"
          :loading="loading"
          @click="join"
          unelevated
          no-caps
          class="w-full"
          mt-4
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
