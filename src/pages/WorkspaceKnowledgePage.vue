<template>
  <q-page-container>
    <q-page
      v-if="userId && !workspaceStore.id"
      flex
      flex-center
      text-on-sur-var
    >
      <div
        text-center
        px-6
      >
        <q-spinner
          v-if="!listReady"
          color="primary"
          size="40px"
        />
        <template v-else>
          <q-icon
            name="sym_o_folder_open"
            size="56px"
          />
          <div
            text-h6
            mt-3
          >
            {{ t('No workspace selected') }}
          </div>
          <div class="text-caption q-mt-md">{{ t('A platform administrator must assign you to a workspace.') }}</div>
        </template>
      </div>
    </q-page>
    <q-page
      v-else-if="workspaceStore.id"
      :style-fn="pageFhStyle"
    >
      <knowledge-list
        :folder-id="folderId"
        h-full
      />
    </q-page>
  </q-page-container>
</template>
<script setup lang="ts">
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import KnowledgeList from 'src/components/KnowledgeList.vue'
import { useRequireLogin } from 'src/composables/require-login'
import { useWorkspaceStore } from 'src/stores/workspace'
import { session } from 'src/utils/identity-client'
import { pageFhStyle } from 'src/utils/functions'
import { t } from 'src/utils/i18n'

useRequireLogin()

const route = useRoute()
const router = useRouter()
const workspaceStore = useWorkspaceStore()
const userId = computed(() => session.value.data?.user.id)
const listReady = computed(() => workspaceStore.workspacesStatus === 'success')

// The workspace root folder is the workspace itself; subfolders are addressed
// through the folderId query parameter on this route.
const folderId = computed(() => {
  const query = route.query.folderId
  return typeof query === 'string' && query ? query : workspaceStore.id ?? ''
})

watch(() => workspaceStore.id, (id, previous) => {
  if (!id || !previous || id === previous) return
  if (route.query.folderId) router.replace({ query: {} })
}, { immediate: true })

</script>
