<template>
  <q-layout view="lHr Lpr lFf">
    <q-drawer
      v-model="uiStateStore.mainDrawerOpen"
      show-if-above
      :width="uiStateStore.mainDrawerWidth"
      :breakpoint="uiStateStore.mainDrawerBreakpoint"
      class="app-rail"
      flex="~ col"
    >
      <q-item
        v-if="userId"
        clickable
        py-1
        data-testid="kb-switcher"
      >
        <template v-if="kbStore.current">
          <q-item-section
            avatar
            pr-3
            ml--1
          >
            <a-avatar :avatar="kbAvatar(kbStore.current)" />
          </q-item-section>
          <q-item-section>
            <q-item-label>
              {{ kbStore.current.name }}
            </q-item-label>
          </q-item-section>
        </template>
        <template v-else-if="kbStore.kbsStatus !== 'success'">
          <q-item-section
            avatar
            pr-3
            ml--1
          >
            <q-skeleton
              type="QAvatar"
              size="27px"
            />
          </q-item-section>
          <q-item-section>
            <q-skeleton
              type="text"
              width="96px"
            />
          </q-item-section>
        </template>
        <template v-else>
          <q-item-section
            avatar
            pr-3
            ml--1
          >
            <a-avatar :avatar="kbAvatar(null)" />
          </q-item-section>
          <q-item-section>
            <q-item-label class="text-secondary">
              未选择知识库
            </q-item-label>
          </q-item-section>
        </template>
        <q-item-section side>
          <q-icon name="sym_o_keyboard_arrow_down" />
        </q-item-section>
        <q-menu>
          <kb-menu-list />
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
            登录/注册
          </q-item-label>
        </q-item-section>
      </q-item>
      <q-separator spaced />
      <template v-if="userId">
        <q-list
          p-2
          flex-1
        >
          <q-item
            to="/"
            exact
            item-rd
            min-h="40px"
            data-testid="rail-nav-ask"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_chat" />
            </q-item-section>
            <q-item-section>
              提问
            </q-item-section>
          </q-item>
          <q-item
            to="/kb"
            item-rd
            min-h="40px"
            data-testid="rail-nav-kb"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_folder" />
            </q-item-section>
            <q-item-section>
              知识库
            </q-item-section>
          </q-item>
          <q-item
            to="/history"
            item-rd
            min-h="40px"
            data-testid="rail-nav-history"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_history" />
            </q-item-section>
            <q-item-section>
              历史
            </q-item-section>
          </q-item>
          <q-item
            to="/connectors"
            item-rd
            min-h="40px"
            data-testid="rail-nav-connectors"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_hub" />
            </q-item-section>
            <q-item-section>
              连接器
            </q-item-section>
          </q-item>
        </q-list>
        <q-list p-2>
          <q-item
            to="/settings"
            item-rd
            min-h="40px"
            data-testid="rail-nav-settings"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_settings" />
            </q-item-section>
            <q-item-section>
              设置
            </q-item-section>
          </q-item>
          <q-item
            v-if="canSeeAdminConsole"
            to="/admin"
            item-rd
            min-h="40px"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_manage_accounts" />
            </q-item-section>
            <q-item-section>
              管理控制台
            </q-item-section>
          </q-item>
          <q-item
            clickable
            item-rd
            min-h="40px"
            hover:text-err
            @click="signOut"
          >
            <q-item-section avatar>
              <q-icon name="sym_o_logout" />
            </q-item-section>
            <q-item-section>
              退出登录
            </q-item-section>
          </q-item>
        </q-list>
      </template>
    </q-drawer>
    <router-view />
    <kb-manage-dialog
      v-if="kbStore.current"
      v-model="kbStore.manageOpen"
      :kb="kbStore.current"
      :initial-section="kbStore.manageSection"
    />
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, provide } from 'vue'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { useKbStore } from 'src/stores/knowledge-base'
import { useUiStateStore } from 'src/stores/ui-state'
import { identityClient, session } from 'src/utils/identity-client'
import { kbAvatar } from 'src/utils/defaults'
import AAvatar from 'src/components/AAvatar.vue'
import KbManageDialog from 'src/components/KbManageDialog.vue'
import KbMenuList from 'src/components/KbMenuList.vue'
import { groundedKey, useGroundedKnowledge } from 'src/composables/use-grounded-knowledge'
import { waitingWorker } from 'app/src-pwa/register-service-worker'

const uiStateStore = useUiStateStore()
const kbStore = useKbStore()
const $q = useQuasar()
const router = useRouter()

// Shared Ask state: streams keep running while the main pane routes from the
// Ask home to /ask/:conversationId.
provide(groundedKey, useGroundedKnowledge(() => kbStore.id))

const userId = computed(() => session.value.data?.user.id)

const adminRoles = ['super_admin', 'platform_admin', 'security_auditor']
const canSeeAdminConsole = computed(() =>
  session.value.data?.user.platformRoles?.some(role => adminRoles.includes(role)) ?? false)

// A background-updated service worker is applied on the next route change so
// users pick up the new build without a manual hard refresh. The admin console
// lives in this same app (`/admin`), reached with an internal navigation.
const stopUpdateGuard = router.beforeEach((to, from) => {
  if (!waitingWorker || to.path === from.path) return
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    location.href = to.fullPath
  }, { once: true })
  waitingWorker.postMessage({ type: 'SKIP_WAITING' })
  // Prevent hanging
  setTimeout(() => {
    location.href = to.fullPath
  }, 3000)
  return false
})
onBeforeUnmount(stopUpdateGuard)

function signOut() {
  $q.dialog({
    title: '退出登录',
    message: '您确定要退出登录吗？',
    cancel: true,
    ok: {
      label: '退出登录',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    await identityClient.signOut()
    kbStore.id = null
    router.push('/auth/sign-in')
  })
}
</script>

<style scoped>
.app-rail {
  background-color: var(--tk-surface);
  border-right: 1px solid var(--tk-border);
}
</style>
