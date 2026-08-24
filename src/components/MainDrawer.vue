<template>
  <q-drawer
    show-if-above
    v-model="uiStateStore.mainDrawerOpen"
    :width="uiStateStore.mainDrawerWidth"
    :breakpoint="uiStateStore.mainDrawerBreakpoint"
    bg-sur-c
    flex
    flex-col
  >
    <q-item
      v-if="user.id"
      clickable
      py-1
    >
      <q-item-section
        avatar
        pr-3
        ml--1
      >
        <a-avatar :avatar="workspaceAvatar(workspaceStore.workspace)" />
      </q-item-section>
      <q-item-section>
        <q-item-label v-if="workspaceStore.workspace">
          {{ workspaceStore.workspace.name }}
        </q-item-label>
        <q-item-label
          v-else
          text-warn
        >
          {{ t('No workspace selected') }}
        </q-item-label>
      </q-item-section>
      <q-item-section side>
        <q-icon name="sym_o_keyboard_arrow_down" />
      </q-item-section>
      <q-menu>
        <workspace-menu-list />
      </q-menu>
    </q-item>
    <q-item
      v-else
      to="/auth/sign-in"
    >
      <q-item-section
        avatar
        min-w-0
      >
        <q-icon name="sym_o_login" />
      </q-item-section>
      <q-item-section>
        <q-item-label>
          {{ t('Sign In / Sign Up') }}
        </q-item-label>
      </q-item-section>
    </q-item>
    <q-separator spaced />
    <folder-tree v-if="workspaceStore.id" />
    <q-space />
    <q-list
      p-2
      text-on-sur-var
    >
      <template v-if="workspaceStore.id">
        <q-item
          clickable
          @click="askKnowledge"
          item-rd
          min-h="40px"
        >
          <q-item-section avatar>
            <q-icon name="sym_o_chat" />
          </q-item-section>
          <q-item-section>
            {{ t('Ask') }}
          </q-item-section>
        </q-item>
        <q-item
          clickable
          @click="searchInWorkspace"
          item-rd
          min-h="40px"
        >
          <q-item-section avatar>
            <q-icon name="sym_o_manage_search" />
          </q-item-section>
          <q-item-section>
            {{ t('Search in Workspace') }}
          </q-item-section>
        </q-item>
        <task-panel-btn
          item-rd
          min-h="40px"
        />
        <q-item
          to="/trash"
          item-rd
          min-h="40px"
        >
          <q-item-section avatar>
            <q-icon name="sym_o_delete" />
          </q-item-section>
          <q-item-section>
            {{ t('Trash') }}
          </q-item-section>
        </q-item>
        <q-item
          to="/workspace"
          item-rd
          min-h="40px"
        >
          <q-item-section avatar>
            <q-icon name="sym_o_manage_accounts" />
          </q-item-section>
          <q-item-section>
            {{ t('Workspace Settings') }}
          </q-item-section>
        </q-item>
        <q-separator spaced />
      </template>
      <div
        flex
        text-on-sur-var
        items-center
      >
        <q-btn
          icon="sym_o_tune"
          :label="t('Personal Settings')"
          to="/settings"
          :class="{ 'route-active': $route.path === '/settings'}"
          flat
          no-caps
        />
        <q-space />
        <dark-switch-btn />
      </div>
    </q-list>
  </q-drawer>
</template>

<script setup lang="ts">
import { t } from 'src/utils/i18n'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import AAvatar from './AAvatar.vue'
import { workspaceAvatar } from 'src/utils/defaults'
import WorkspaceMenuList from './WorkspaceMenuList.vue'
import FolderTree from './FolderTree.vue'
import DarkSwitchBtn from './DarkSwitchBtn.vue'
import { user } from 'src/utils/zero-session'
import { useAskKnowledge } from 'src/composables/ask-knowledge'
import TaskPanelBtn from './TaskPanelBtn.vue'

const uiStateStore = useUiStateStore()
const workspaceStore = useWorkspaceStore()
const askKnowledge = useAskKnowledge()

function searchInWorkspace() {
  uiStateStore.searchDialogOpen = true
}
</script>
