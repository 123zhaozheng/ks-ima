<template>
  <q-page-container>
    <q-page
      class="admin-page"
      :style-fn="pageFhStyle"
    >
      <!-- Backend health stays reachable in the admin section via the shell TopBar. -->
      <teleport
        defer
        to="#topbar-actions"
      >
        <system-status-indicator />
      </teleport>
      <nav
        class="admin-nav"
        aria-label="管理控制台"
      >
        <div class="admin-nav-group">
          管理
        </div>
        <q-list class="admin-nav-list">
          <q-item
            v-if="canManageUsers"
            to="/admin/users"
            class="admin-nav-item"
            data-testid="admin-nav-users"
          >
            <q-item-section avatar>
              <q-icon
                name="sym_o_group"
                size="18px"
              />
            </q-item-section>
            <q-item-section>用户</q-item-section>
          </q-item>
          <q-item
            to="/admin/knowledge-bases"
            class="admin-nav-item"
            data-testid="admin-nav-knowledge-bases"
          >
            <q-item-section avatar>
              <q-icon
                name="sym_o_deployed_code"
                size="18px"
              />
            </q-item-section>
            <q-item-section>知识库</q-item-section>
          </q-item>
          <q-item
            v-if="canReadModelGovernance"
            to="/admin/models"
            class="admin-nav-item"
            data-testid="admin-nav-models"
          >
            <q-item-section avatar>
              <q-icon
                name="sym_o_neurology"
                size="18px"
              />
            </q-item-section>
            <q-item-section>模型配置</q-item-section>
          </q-item>
          <q-item
            to="/admin/audit"
            class="admin-nav-item"
            data-testid="admin-nav-audit"
          >
            <q-item-section avatar>
              <q-icon
                name="sym_o_history"
                size="18px"
              />
            </q-item-section>
            <q-item-section>审计</q-item-section>
          </q-item>
        </q-list>
        <q-list class="admin-nav-list admin-nav-bottom">
          <q-item
            v-if="canManageSettings"
            clickable
            class="admin-nav-item"
            data-testid="admin-nav-settings"
            @click="openSettings"
          >
            <q-item-section avatar>
              <q-icon
                name="sym_o_settings"
                size="18px"
              />
            </q-item-section>
            <q-item-section>设置</q-item-section>
          </q-item>
        </q-list>
      </nav>
      <section class="admin-content">
        <router-view />
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useQuasar } from 'quasar'
import SystemStatusIndicator from '../components/SystemStatusIndicator.vue'
import UpdateSettingsDialog from '../components/UpdateSettingsDialog.vue'
import { session } from 'src/utils/identity-client'
import { pageFhStyle } from 'src/utils/functions'

const canManageUsers = computed(() => session.value.data?.user.platformRoles.includes('super_admin') || session.value.data?.user.platformRoles.includes('platform_admin'))
const canManageSettings = canManageUsers
const canReadModelGovernance = computed(() => canManageUsers.value || session.value.data?.user.platformRoles.includes('security_auditor'))

const $q = useQuasar()
function openSettings() {
  $q.dialog({
    component: UpdateSettingsDialog,
  })
}
</script>

<style>
/*
 * Admin section chrome. Global flat selectors (Chrome 109: no nesting)
 * because pages render into .admin-content through the router view.
 * Palette values come from the shared --tk-* tokens only.
 */
.admin-page {
  display: flex;
  min-height: 0;
  background-color: var(--tk-bg);
}

/* Compact secondary nav: KB workspace pane language, 180-200px. */
.admin-nav {
  display: flex;
  flex-direction: column;
  flex: 0 0 188px;
  width: 188px;
  min-height: 0;
  padding: var(--tk-space-3) var(--tk-space-2);
  overflow-y: auto;
  background-color: var(--tk-surface);
  border-right: 1px solid var(--tk-border);
}

.admin-nav-group {
  padding: 0 var(--tk-space-3) var(--tk-space-1);
  font-size: var(--tk-font-size-xs);
  font-weight: var(--tk-weight-medium);
  color: var(--tk-text-tertiary);
}

.admin-nav-list {
  padding: 0;
}

.admin-nav-bottom {
  margin-top: auto;
  padding-top: var(--tk-space-2);
  border-top: 1px solid var(--tk-border-subtle);
}

.q-item.admin-nav-item {
  min-height: 34px;
  padding: 6px var(--tk-space-3);
  border-radius: var(--tk-radius);
  font-size: var(--tk-font-size-sm);
  color: var(--tk-text-secondary);
}

.admin-nav-item .q-item__section--avatar {
  min-width: 26px;
}

.admin-nav-item:hover {
  background-color: var(--tk-bg);
}

/* Declared after the hover rule so the active fill wins when both apply. */
.admin-nav-item.q-router-link--active {
  font-weight: var(--tk-weight-medium);
  color: var(--tk-text);
  background-color: var(--tk-accent-soft);
}

.admin-nav-item.q-router-link--active .q-icon {
  color: var(--tk-accent);
}

.admin-content {
  flex: 1 1 0;
  min-width: 0;
  min-height: 0;
  padding: var(--tk-space-5) var(--tk-space-6);
  overflow-y: auto;
}

/* Table pages stay one readable column instead of stretching edge to edge. */
.admin-content > * {
  width: 100%;
  max-width: 1160px;
  margin: 0 auto;
}

/* Shared tables: white card with a subtle hairline, calm rows, muted headers. */
.admin-content .q-table__card {
  background-color: var(--tk-surface-white);
  border: 1px solid var(--tk-border-subtle);
  border-radius: var(--tk-radius-lg);
}

.admin-content .q-table thead,
.admin-content .q-table tr,
.admin-content .q-table th,
.admin-content .q-table td {
  border-color: var(--tk-border-subtle);
}

.admin-content .q-table thead th {
  height: 40px;
  font-size: 13px;
  font-weight: var(--tk-weight-medium);
  color: var(--tk-text-secondary);
}

.admin-content .q-table tbody td {
  height: 44px;
  font-size: 13px;
  color: var(--tk-text);
}

.admin-content .q-table__bottom {
  min-height: 44px;
  border-top-color: var(--tk-border-subtle);
  color: var(--tk-text-secondary);
}

.admin-content .q-table .tk-pane-empty {
  padding: var(--tk-space-12) var(--tk-space-6);
}

/* Page toolbars: one centered row, every control at the 36px height. */
.admin-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--tk-space-2);
}

.admin-toolbar > .q-input {
  width: 240px;
}

.admin-toolbar > .q-select {
  width: 200px;
}

.admin-toolbar .q-field--dense .q-field__control,
.admin-toolbar .q-field--dense .q-field__marginal {
  height: 36px;
  min-height: 36px;
}

/* Admin pages keep the main-app button hierarchy at the denser 36px spec. */
.admin-content .tk-btn-primary.tk-btn-primary,
.admin-content .tk-btn-secondary.tk-btn-secondary,
.admin-content .tk-btn-ghost.tk-btn-ghost,
.admin-content .tk-btn-danger-ghost.tk-btn-danger-ghost {
  min-height: 36px;
}

/* Compact inline banners: radius 8, info tone; no big color blocks. */
.admin-banner {
  display: flex;
  align-items: center;
  gap: var(--tk-space-2);
  padding: var(--tk-space-2) var(--tk-space-3);
  border-radius: var(--tk-radius);
  font-size: 13px;
  line-height: var(--tk-lh-body);
  color: var(--tk-text-secondary);
  background-color: var(--tk-accent-soft);
}

.admin-banner-error {
  color: var(--tk-danger);
  background-color: var(--tk-danger-soft);
}

.admin-banner .q-btn {
  min-height: 24px;
  padding: 0 var(--tk-space-2);
  font-size: 13px;
  color: inherit;
}
</style>
