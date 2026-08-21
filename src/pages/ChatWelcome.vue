<template>
  <welcome-wrapper>
    <q-card
      flat
      bg-sur
      max-w="600px"
    >
      <q-card-section>
        <div class="text-h5">
          {{ t('AI Chat') }}
        </div>
      </q-card-section>
      <q-card-section>
        <div>
          {{ t('Modify your default settings below.') }}
        </div>
        <div mt-2>
          {{ t('Click "New Chat" in the right sidebar to start a chat with AI.') }}
        </div>
      </q-card-section>
      <q-card-section>
        <div
          flex
          gap-2
        >
          <send-key-select
            :label="t('Send Message Shortcut')"
            filled
            class="flex-1"
            :model-value="perfsStore.perfs.sendMessageKey"
            @update:model-value="perfsStore.update({
              updates: { sendMessageKey: $event },
              scope: 'user',
            })"
          />
          <model-select
            :workspace-id="workspaceStore.id"
            :label="t('Default Model')"
            :model-value="conf.chatModelId"
            @update:model-value="update('chatModelId', $event)"
            filled
            class="flex-1"
          />
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <q-item-label header>
            {{ t('Further') }}
          </q-item-label>
          <common-item
            :label="t('Add custom model providers')"
            :caption="addProviderCaption"
            clickable
            @click="addProvider"
            rd
          />
        </q-list>
      </q-card-section>
    </q-card>
  </welcome-wrapper>
</template>

<script setup lang="ts">
import CommonItem from 'src/components/CommonItem.vue'
import ModelSelect from 'src/components/ModelSelect.vue'
import SendKeySelect from 'src/components/SendKeySelect.vue'
import { useRootEntityConf } from 'src/composables/entity-conf'
import { useRunShortcut } from 'src/composables/run-shortcut'
import { t } from 'src/utils/i18n'
import { useActiveEntitiesStore } from 'src/stores/active-entities'
import WelcomeWrapper from './WelcomeWrapper.vue'
import { useWorkspaceStore } from 'src/stores/workspace'
import { usePerfsStore } from 'src/stores/perfs'

const { conf, update } = useRootEntityConf()

const perfsStore = usePerfsStore()

const runShortcut = useRunShortcut()
const activeEntitiesStore = useActiveEntitiesStore()
function addProvider() {
  const shortcut = activeEntitiesStore.shortcuts.find(s => s.type === 'provider')
  shortcut && runShortcut(shortcut)
}

const addProviderCaption = t("Set a custom API key and baseURL; custom models do not consume your workspace's AI quota.")
const workspaceStore = useWorkspaceStore()
</script>
