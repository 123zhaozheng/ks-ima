<template>
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
            对话列表加载失败。
          </div>
          <q-btn
            flat
            dense
            color="primary"
            label="重试"
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
            暂无对话
          </div>
          <div
            class="text-caption"
            mt-2
          >
            你发起的对话将显示在这里。
          </div>
          <q-btn
            unelevated
            no-caps
            class="tk-cta"
            label="开始对话"
            mt-4
            data-testid="history-go-ask"
            @click="router.push('/')"
          />
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
              {{ conversation.kbName }} · 更新于 {{ new Date(conversation.updatedAt).toLocaleString() }}
              <template v-if="conversation.lifecycle === 'archived'">
                · 已归档
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
                    <q-item-section>重命名</q-item-section>
                  </q-item>
                  <q-item
                    v-close-popup
                    clickable
                    @click="toggleArchive(conversation)"
                  >
                    <q-item-section avatar>
                      <q-icon :name="conversation.lifecycle === 'archived' ? 'sym_o_unarchive' : 'sym_o_archive'" />
                    </q-item-section>
                    <q-item-section>{{ conversation.lifecycle === 'archived' ? '恢复' : '归档' }}</q-item-section>
                  </q-item>
                  <q-item
                    v-close-popup
                    clickable
                    @click="remove(conversation)"
                  >
                    <q-item-section avatar>
                      <q-icon name="sym_o_delete" />
                    </q-item-section>
                    <q-item-section>删除</q-item-section>
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
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'

type Conversation = components['schemas']['ConversationResponse']

useRequireLogin()

const router = useRouter()
const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()

// User-level history: one list across every knowledge base the user belongs
// to; each row carries the knowledge base it lives in.
const grounded = inject(groundedKey) ?? useGroundedKnowledge(() => kbStore.id)
const conversations = grounded.conversations

const rows = computed(() => conversations.data.value?.items ?? [])

function open(conversationId: string) {
  router.push(`/ask/${conversationId}`)
}

async function refresh() {
  await queryClient.invalidateQueries({ queryKey: ['grounded', 'conversations'] })
}

function rename(conversation: Conversation) {
  $q.dialog({
    title: '重命名对话',
    prompt: { model: conversation.title, type: 'text' },
    cancel: true,
  }).onOk(async (title: string) => {
    const next = title.trim()
    if (!next || next === conversation.title) return
    try {
      await groundedClient.updateConversation(conversation.kbId, conversation.id, { title: next, expectedVersion: conversation.version })
      await refresh()
    } catch (error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '重命名失败') })
    }
  })
}

function toggleArchive(conversation: Conversation) {
  const archived = conversation.lifecycle !== 'archived'
  groundedClient.updateConversation(conversation.kbId, conversation.id, { archived, expectedVersion: conversation.version })
    .then(refresh)
    .catch(error => {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '归档失败') })
    })
}

function remove(conversation: Conversation) {
  $q.dialog({
    title: '删除对话',
    message: `确定要删除“${conversation.title}”吗？此操作无法撤销。`,
    cancel: true,
    ok: { label: '删除', color: 'negative', flat: true },
  }).onOk(() => {
    groundedClient.deleteConversation(conversation.kbId, conversation.id, conversation.version)
      .then(refresh)
      .catch(error => {
        Notify.create({ type: 'negative', message: apiErrorMessage(error, '删除失败') })
      })
  })
}
</script>

<style scoped>
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
