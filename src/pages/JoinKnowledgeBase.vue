<template>
  <q-page-container>
    <q-page
      class="join-page"
      flex="~ col"
      flex-center
    >
      <div class="tk-card join-card">
        <div class="join-title">
          {{ t('Join knowledge base') }}
        </div>
        <template v-if="isPending">
          <div
            class="join-state"
            data-testid="join-loading"
          >
            <q-spinner
              size="22px"
              color="primary"
            />
            <span class="text-secondary">{{ t('Loading…') }}</span>
          </div>
        </template>
        <template v-else-if="!userId">
          <div class="join-state">
            {{ t('Sign in to join this knowledge base.') }}
          </div>
          <q-btn
            unelevated
            color="primary"
            :label="t('Sign In')"
            data-testid="join-sign-in"
            @click="goSignIn"
          />
        </template>
        <template v-else-if="state === 'joining'">
          <div
            class="join-state"
            data-testid="join-joining"
          >
            <q-spinner
              size="22px"
              color="primary"
            />
            <span class="text-secondary">{{ t('Joining…') }}</span>
          </div>
        </template>
        <template v-else-if="state === 'failed'">
          <div
            class="join-state"
            data-testid="join-error"
          >
            {{ apiErrorMessage(error, 'Failed to join knowledge base') }}
          </div>
          <q-btn
            unelevated
            color="primary"
            :label="t('Back')"
            data-testid="join-back"
            @click="router.replace('/kb')"
          />
        </template>
      </div>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Notify } from 'quasar'
import { useRoute, useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import { identityClient, session } from 'src/utils/identity-client'
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { t } from 'src/utils/i18n'

const props = defineProps<{
  token: string
}>()

const route = useRoute()
const router = useRouter()
const queryClient = useQueryClient()
const kbStore = useKbStore()

const isPending = computed(() => session.value.isPending)
const userId = computed(() => session.value.data?.user.id ?? null)
const state = ref<'joining' | 'failed'>('joining')
const error = ref<unknown>(null)
let attempted = false

watch([userId, isPending], ([id, pending]) => {
  if (pending || !id || attempted) return
  attempted = true
  join()
}, { immediate: true })

async function join() {
  state.value = 'joining'
  const result = await identityClient.acceptKbShareLink(props.token)
  if (result.error || !result.data) {
    error.value = result.error ?? new Error('Join failed')
    state.value = 'failed'
    return
  }
  Notify.create({ type: 'positive', message: t('Joined knowledge base') })
  // Refresh membership, select the joined knowledge base, and open it.
  await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
  kbStore.switchKb(result.data.id)
  router.replace('/kb')
}

function goSignIn() {
  router.push({ path: '/auth/sign-in', query: { redirect: route.fullPath } })
}
</script>

<style scoped>
.join-page {
  padding: var(--tk-space-4);
}

.join-card {
  width: min(92vw, 420px);
  padding: var(--tk-space-8) var(--tk-space-6);
  display: flex;
  flex-direction: column;
  gap: var(--tk-space-4);
}

.join-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--tk-text);
}

.join-state {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  color: var(--tk-text);
  min-height: 32px;
}
</style>
