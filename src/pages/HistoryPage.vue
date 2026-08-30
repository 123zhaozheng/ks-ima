<template>
  <q-header class="history-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('History') }}</q-toolbar-title>
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page
      v-if="conversations.isError.value"
      flex
      flex-center
    >
      <q-card
        flat
        bordered
        class="history-state"
      >
        <div
          text-center
          px-8
          py-6
        >
          <q-icon
            name="sym_o_cloud_off"
            size="40px"
          />
          <div mt-3>
            {{ t('Conversations could not be loaded.') }}
          </div>
          <q-btn
            flat
            dense
            color="primary"
            :label="t('Retry')"
            mt-2
            @click="conversations.refetch()"
          />
        </div>
      </q-card>
    </q-page>
    <q-page
      v-else-if="conversations.isLoading.value"
      flex
      flex-center
    >
      <q-spinner color="primary" />
    </q-page>
    <q-page
      v-else-if="rows.length === 0"
      flex
      flex-center
    >
      <q-card
        flat
        bordered
        class="history-state"
      >
        <div
          text-center
          px-8
          py-6
        >
          <q-icon
            name="sym_o_history"
            size="48px"
          />
          <div mt-3>
            {{ t('No conversations yet') }}
          </div>
          <div
            class="text-caption"
            mt-2
          >
            {{ t('Conversations you start will appear here.') }}
          </div>
        </div>
      </q-card>
    </q-page>
    <q-page v-else>
      <q-list
        class="history-list"
        separator
        data-testid="history-list"
      >
        <q-item
          v-for="conversation in rows"
          :key="conversation.id"
          clickable
          class="history-item"
          data-testid="history-item"
          @click="open(conversation.id)"
        >
          <q-item-section avatar>
            <q-icon name="sym_o_chat" />
          </q-item-section>
          <q-item-section>
            <q-item-label
              text-ellipsis
              whitespace-nowrap
              overflow-hidden
            >
              {{ conversation.title }}
            </q-item-label>
            <q-item-label caption>
              {{ t('Updated {0}', new Date(conversation.updatedAt).toLocaleString()) }}
              <template v-if="conversation.lifecycle === 'archived'">
                · {{ t('Archived') }}
              </template>
            </q-item-label>
          </q-item-section>
          <q-item-section
            side
            @click.stop
          >
            <q-btn
              flat
              dense
              round
              icon="sym_o_more_vert"
              data-testid="history-item-menu"
            >
              <q-menu>
                <q-list dense>
                  <q-item
                    v-close-popup
                    clickable
                    @click="rename(conversation)"
                  >
                    <q-item-section avatar>
                      <q-icon name="sym_o_edit" />
                    </q-item-section>
                    <q-item-section>{{ t('Rename') }}</q-item-section>
                  </q-item>
                  <q-item
                    v-close-popup
                    clickable
                    @click="toggleArchive(conversation)"
                  >
                    <q-item-section avatar>
                      <q-icon :name="conversation.lifecycle === 'archived' ? 'sym_o_unarchive' : 'sym_o_archive'" />
                    </q-item-section>
                    <q-item-section>{{ conversation.lifecycle === 'archived' ? t('Restore') : t('Archive') }}</q-item-section>
                  </q-item>
                  <q-item
                    v-close-popup
                    clickable
                    @click="remove(conversation)"
                  >
                    <q-item-section avatar>
                      <q-icon name="sym_o_delete" />
                    </q-item-section>
                    <q-item-section>{{ t('Delete') }}</q-item-section>
                  </q-item>
                </q-list>
              </q-menu>
            </q-btn>
          </q-item-section>
        </q-item>
      </q-list>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, inject } from 'vue'
import { useRouter } from 'vue-router'
import { Notify, useQuasar } from 'quasar'
import { useQueryClient } from '@tanstack/vue-query'
import { groundedClient } from 'src/api/grounded-client'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { useRequireLogin } from 'src/composables/require-login'
import { useUiStateStore } from 'src/stores/ui-state'
import { useWorkspaceStore } from 'src/stores/workspace'
import { t } from 'src/utils/i18n'

type Conversation = components['schemas']['ConversationResponse']

useRequireLogin()

const router = useRouter()
const $q = useQuasar()
const queryClient = useQueryClient()
const workspaceStore = useWorkspaceStore()
const uiStateStore = useUiStateStore()

const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => workspaceStore.id)
const conversations = grounded.conversations

const rows = computed(() => conversations.data.value?.items ?? [])

function open(conversationId: string) {
  router.push(`/ask/${conversationId}`)
}

async function refresh() {
  if (!workspaceStore.id) return
  await queryClient.invalidateQueries({ queryKey: ['grounded', 'workspace', workspaceStore.id, 'conversations'] })
}

function rename(conversation: Conversation) {
  $q.dialog({
    title: t('Rename conversation'),
    prompt: { model: conversation.title, type: 'text' },
    cancel: true,
  }).onOk(async (title: string) => {
    const next = title.trim()
    if (!next || next === conversation.title || !workspaceStore.id) return
    try {
      await groundedClient.updateConversation(workspaceStore.id, conversation.id, { title: next, expectedVersion: conversation.version })
      await refresh()
    } catch (error) {
      Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Rename failed') })
    }
  })
}

function toggleArchive(conversation: Conversation) {
  if (!workspaceStore.id) return
  const archived = conversation.lifecycle !== 'archived'
  groundedClient.updateConversation(workspaceStore.id, conversation.id, { archived, expectedVersion: conversation.version })
    .then(refresh)
    .catch(error => {
      Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Archive failed') })
    })
}

function remove(conversation: Conversation) {
  $q.dialog({
    title: t('Delete conversation'),
    message: t('Are you sure you want to delete "{0}"?', conversation.title),
    cancel: true,
    ok: { label: t('Delete'), color: 'negative', flat: true },
  }).onOk(() => {
    if (!workspaceStore.id) return
    groundedClient.deleteConversation(workspaceStore.id, conversation.id, conversation.version)
      .then(refresh)
      .catch(error => {
        Notify.create({ type: 'negative', message: error instanceof Error ? error.message : t('Delete failed') })
      })
  })
}
</script>

<style scoped>
.history-header {
  background-color: var(--tk-surface);
  color: var(--tk-text);
}

.history-list {
  max-width: 860px;
  margin: 0 auto;
  padding: var(--tk-space-4);
}

.history-item {
  border-radius: var(--tk-radius);
}

.history-item:hover {
  background-color: var(--tk-surface);
}

.history-state {
  border-radius: var(--tk-radius-lg);
  border-color: var(--tk-border);
  color: var(--tk-text-secondary);
}
</style>
