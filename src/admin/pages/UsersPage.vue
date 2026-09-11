<template>
  <div>
    <div class="admin-toolbar">
      <q-input
        v-model="searchValue"
        :debounce="200"
        placeholder="搜索用户"
        outlined
        dense
      >
        <template #prepend>
          <q-icon
            name="sym_o_search"
            size="18px"
          />
        </template>
        <template #append>
          <q-btn-dropdown
            flat
            dense
            :label="searchFieldLabel"
          >
            <q-list>
              <menu-item
                label="邮箱"
                @click="searchField = 'email'"
              />
              <menu-item
                label="名称"
                @click="searchField = 'name'"
              />
            </q-list>
          </q-btn-dropdown>
        </template>
      </q-input>
      <q-btn
        v-if="canManageUsers"
        icon="sym_o_add"
        label="创建用户"
        @click="createUser"
        unelevated
        no-caps
        class="tk-btn-primary"
        ml-a
        shrink-0
      />
    </div>
    <div
      v-if="session.data?.user.platformRoles.includes('super_admin')"
      class="admin-banner"
      mt-2
    >
      超级管理员角色管理已启用。
    </div>
    <div
      v-if="errorMessage"
      class="admin-banner admin-banner-error"
      mt-2
    >
      {{ errorMessage }} <q-btn
        icon="refresh"
        flat
        dense
        @click="refresh"
      />
    </div>
    <q-table
      class="users-table"
      ref="tableRef"
      :rows
      :columns
      row-key="id"
      v-model:pagination="pagination"
      :loading
      binary-state-sort
      @request="onRequest"
      :rows-per-page-options="[10, 20, 50, 100]"
      flat
      mt-4
    >
      <template #body-cell-actions="props">
        <q-td :props>
          <template v-if="canManageUsers">
            <q-btn
              icon="sym_o_edit"
              title="编辑信息"
              flat
              round
              size="sm"
              @click="editUser(props.row)"
            />
            <q-btn
              icon="sym_o_more_vert"
              title="操作"
              flat
              round
              size="sm"
            >
              <q-menu>
                <q-list>
                  <menu-item
                    label="查看知识库"
                    :to="`/knowledge-bases?ownerId=${props.row.id}`"
                  />
                  <menu-item
                    label="重置密码"
                    @click="resetPassword(props.row)"
                  />
                  <menu-item
                    label="撤销会话"
                    @click="revokeSessions(props.row)"
                  />
                  <menu-item
                    v-if="props.row.isActive"
                    label="停用用户"
                    @click="banUser(props.row)"
                  />
                  <menu-item
                    v-else
                    label="恢复用户"
                    @click="identityClient.restoreUser(props.row.id).then(refresh)"
                  />
                  <menu-item
                    label="重置 TOTP"
                    @click="resetTotp(props.row)"
                  />
                  <template v-if="session.data?.user.platformRoles.includes('super_admin')">
                    <q-separator />
                    <menu-item
                      label="授予平台管理员"
                      @click="identityClient.grantRole(props.row.id, 'platform_admin').then(refresh)"
                    />
                    <menu-item
                      label="授予安全审计员"
                      @click="identityClient.grantRole(props.row.id, 'security_auditor').then(refresh)"
                    />
                    <menu-item
                      label="撤销平台管理员"
                      @click="identityClient.revokeRole(props.row.id, 'platform_admin').then(refresh)"
                    />
                    <menu-item
                      label="撤销安全审计员"
                      @click="identityClient.revokeRole(props.row.id, 'security_auditor').then(refresh)"
                    />
                  </template>
                  <menu-item
                    label="删除用户"
                    @click="deleteUser(props.row)"
                    hover:text-err
                  />
                </q-list>
              </q-menu>
            </q-btn>
          </template>
        </q-td>
      </template>
      <template #no-data>
        <pane-empty-state
          icon="sym_o_group"
          title="暂无用户"
        />
      </template>
    </q-table>
  </div>
</template>

<script setup lang="ts">
import type { QTableColumn, QTableProps } from 'quasar'
import { useQuasar } from 'quasar'
import { identityClient, session } from 'src/utils/identity-client'
import { computed, onMounted, ref, watch } from 'vue'
import UpdateUserDialog from '../components/UpdateUserDialog.vue'
import MenuItem from 'src/components/MenuItem.vue'
import PaneEmptyState from 'src/components/PaneEmptyState.vue'
import BanUserDialog from '../components/BanUserDialog.vue'
import CreateUserDialog from '../components/CreateUserDialog.vue'
import type { components } from 'src/api/generated/schema'

type UserWithRole = components['schemas']['IdentityUser']

const columns: QTableColumn[] = [
  { name: 'id', label: 'ID', field: 'id', sortable: true, align: 'left' },
  { name: 'name', label: '姓名', field: 'displayName', sortable: true },
  { name: 'email', label: '邮箱', field: 'email', sortable: true },
  { name: 'roles', label: '角色', field: row => row.platformRoles.join(', '), sortable: true },
  { name: 'actions', label: '操作', field: () => null },
]

const rows = ref<UserWithRole[]>([])
const searchValue = ref('')
const searchField = ref<('email' | 'name')>('email')
const searchFieldLabel = computed(() => searchField.value === 'email' ? '邮箱' : '名称')
const loading = ref(false)
const errorMessage = ref('')
const canManageUsers = computed(() => session.value.data?.user.platformRoles.some(role => role === 'super_admin' || role === 'platform_admin') ?? false)
const pagination = ref<QTableProps['pagination']>({
  sortBy: 'createdAt',
  descending: true,
  page: 1,
  rowsPerPage: 20,
})

const $q = useQuasar()
const onRequest: QTableProps['onRequest'] = async ({
  pagination: { sortBy, descending, page, rowsPerPage },
}) => {
  loading.value = true
  const { data, error } = await identityClient.listUsers(searchValue.value ?? '')
  loading.value = false
  if (error) {
    errorMessage.value = error.message
    console.error(error)
    $q.notify({
      message: `无法获取用户：${error.message}`,
      color: 'negative',
    })
    return
  }
  if (!data) return
  pagination.value = {
    sortBy,
    descending,
    page,
    rowsPerPage,
    rowsNumber: data.items.length,
  }
  rows.value = data.items
}

const tableRef = ref()
const refresh = () => tableRef.value?.requestServerInteraction()
onMounted(refresh)
watch([searchValue, searchField], refresh)

function createUser() {
  $q.dialog({
    component: CreateUserDialog,
  }).onOk(refresh)
}
function editUser(user: UserWithRole) {
  $q.dialog({
    component: UpdateUserDialog,
    componentProps: {
      user,
    },
  }).onOk(refresh)
}
function resetPassword({ id, displayName }: UserWithRole) {
  $q.dialog({
    title: '重置密码',
    message: `为用户“${displayName}”设置新密码：`,
    prompt: {
      model: '',
      type: 'password',
    },
    cancel: true,
  }).onOk(newPassword => {
    identityClient.setPassword(id, newPassword).catch(err => {
      console.error(err)
      $q.notify({
        message: `重置密码失败：${err.message}`,
        color: 'negative',
      })
    })
  })
}
function resetTotp({ id }: UserWithRole) {
  identityClient.resetTotp(id).then(refresh)
}
function revokeSessions({ id, displayName }: UserWithRole) {
  $q.dialog({
    title: '撤销会话',
    message: `您确定要撤销“${displayName}”的所有会话吗？`,
    cancel: true,
    ok: '撤销',
  }).onOk(() => {
    identityClient.revokeSessions(id).catch(err => {
      console.error(err)
      $q.notify({
        message: `无法撤销会话：${err.message}`,
        color: 'negative',
      })
    })
  })
}
function banUser(user: UserWithRole) {
  $q.dialog({
    component: BanUserDialog,
    componentProps: {
      user,
    },
  }).onOk(refresh)
}
function deleteUser({ id, displayName }: UserWithRole) {
  $q.dialog({
    title: '删除用户',
    message: `确定要删除用户"${displayName}"吗？注意：必须先删除该用户创建的所有知识库，才能删除该用户。`,
    cancel: true,
    ok: {
      label: '删除',
      color: 'negative',
      flat: true,
    },
  }).onOk(() => {
    identityClient.deleteUser(id).then(refresh).catch(err => {
      console.error(err)
      $q.notify({
        message: `无法删除用户：${err.message}`,
        color: 'negative',
      })
    })
  })
}
</script>
<style lang="scss">
/* :deep — the cells render inside QTable, so scoped attributes never reach them. */
.users-table :deep(th:last-child),
.users-table :deep(td:last-child) {
  position: sticky;
  right: 0;
  z-index: 1;
  background-color: var(--tk-surface-white);
  color: var(--tk-text-secondary);
}
</style>
