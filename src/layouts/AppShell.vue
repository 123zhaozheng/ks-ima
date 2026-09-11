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
        class="rail-item rail-switcher"
        data-testid="kb-switcher"
      >
        <q-item-section class="rail-item-icon">
          <a-avatar
            v-if="kbStore.current"
            :avatar="kbAvatar(kbStore.current)"
          />
          <q-skeleton
            v-else-if="kbStore.kbsStatus !== 'success'"
            type="QAvatar"
            size="27px"
          />
          <a-avatar
            v-else
            :avatar="kbAvatar(null)"
          />
        </q-item-section>
        <q-tooltip
          anchor="center right"
          self="center left"
          :offset="[10, 0]"
        >
          {{ kbStore.current?.name ?? '未选择知识库' }}
        </q-tooltip>
        <q-menu>
          <kb-menu-list />
        </q-menu>
      </q-item>
      <q-item
        v-else
        to="/auth/sign-in"
        class="rail-item"
      >
        <q-item-section class="rail-item-icon">
          <q-icon
            name="sym_o_login"
            size="22px"
          />
        </q-item-section>
        <q-tooltip
          anchor="center right"
          self="center left"
          :offset="[10, 0]"
        >
          登录/注册
        </q-tooltip>
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
            class="rail-item"
            data-testid="rail-nav-ask"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_chat"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              提问
            </q-tooltip>
          </q-item>
          <q-item
            to="/kb"
            class="rail-item"
            data-testid="rail-nav-kb"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_folder"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              知识库
            </q-tooltip>
          </q-item>
          <q-item
            to="/history"
            class="rail-item"
            data-testid="rail-nav-history"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_history"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              历史
            </q-tooltip>
          </q-item>
          <q-item
            to="/connectors"
            class="rail-item"
            data-testid="rail-nav-connectors"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_hub"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              连接器
            </q-tooltip>
          </q-item>
        </q-list>
        <q-list p-2>
          <q-item
            to="/settings"
            class="rail-item"
            data-testid="rail-nav-settings"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_settings"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              设置
            </q-tooltip>
          </q-item>
          <q-item
            v-if="canSeeAdminConsole"
            to="/admin"
            class="rail-item"
            data-testid="rail-nav-admin"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_manage_accounts"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              管理控制台
            </q-tooltip>
          </q-item>
          <q-item
            clickable
            class="rail-item hover:text-err"
            @click="signOut"
          >
            <q-item-section class="rail-item-icon">
              <q-icon
                name="sym_o_logout"
                size="22px"
              />
            </q-item-section>
            <q-tooltip
              anchor="center right"
              self="center left"
              :offset="[10, 0]"
            >
              退出登录
            </q-tooltip>
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

/* Compact icon-forward rail: each row centers a single icon and reveals its
   Chinese label through a tooltip on hover. */
.rail-item {
  min-height: 44px;
  padding: 0 var(--tk-space-1);
  border-radius: var(--tk-radius);
  justify-content: center;
}

.rail-item-icon {
  min-width: 0;
  align-items: center;
  justify-content: center;
}

.rail-switcher {
  min-height: 52px;
}
</style>
