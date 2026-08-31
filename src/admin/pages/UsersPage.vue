<template>
  <q-page-container>
    <q-page p-4>
      <div
        flex
        gap-2
      >
        <q-input
          v-model="searchValue"
          :debounce="200"
          :placeholder="t('Search users')"
          dense
        >
          <template #append>
            <q-btn-dropdown
              flat
              dense
              :label="searchField"
            >
              <q-list>
                <menu-item
                  label="Email"
                  @click="searchField = 'email'"
                />
                <menu-item
                  label="Name"
                  @click="searchField = 'name'"
                />
              </q-list>
            </q-btn-dropdown>
          </template>
        </q-input>
        <q-btn
          v-if="canManageUsers"
          icon="sym_o_add"
          :label="t('Create User')"
          @click="createUser"
          unelevated
          bg-pri-c
          text-on-pri-c
          no-caps
          ml-a
          shrink-0
        />
      </div>
      <q-banner
        v-if="session.data?.user.platformRoles.includes('super_admin')"
        dense
        mt-2
      >
        Super administrator role management enabled.
      </q-banner>
      <q-banner
        v-if="errorMessage"
        bg-err-c
        text-on-err-c
        mt-2
      >
        {{ errorMessage }} <q-btn
          icon="refresh"
          flat
          @click="refresh"
        />
      </q-banner>
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
        bg-sur-c-low
        mt-4
      >
        <template #body-cell-actions="props">
          <q-td
            :props
            text-on-sur-var
          >
            <template v-if="canManageUsers">
              <q-btn
                icon="sym_o_edit"
                :title="t('Edit Info')"
                flat
                round
                size="sm"
                @click="editUser(props.row)"
              />
              <q-btn
                icon="sym_o_more_vert"
                :title="t('Actions')"
                flat
                round
                size="sm"
              >
                <q-menu>
                  <q-list>
                    <menu-item
                      :label="t('View knowledge bases')"
                      :to="`/knowledge-bases?ownerId=${props.row.id}`"
                    />
                    <menu-item
                      :label="t('Reset Password')"
                      @click="resetPassword(props.row)"
                    />
                    <menu-item
                      :label="t('Revoke Sessions')"
                      @click="revokeSessions(props.row)"
                    />
                    <menu-item
                      v-if="props.row.isActive"
                      :label="t('Disable User')"
                      @click="banUser(props.row)"
                    />
                    <menu-item
                      v-else
                      :label="t('Restore User')"
                      @click="identityClient.restoreUser(props.row.id).then(refresh)"
                    />
                    <menu-item
                      :label="t('Reset TOTP')"
                      @click="resetTotp(props.row)"
                    />
                    <template v-if="session.data?.user.platformRoles.includes('super_admin')">
                      <q-separator />
                      <menu-item
                        label="Grant platform admin"
                        @click="identityClient.grantRole(props.row.id, 'platform_admin').then(refresh)"
                      />
                      <menu-item
                        label="Grant security auditor"
                        @click="identityClient.grantRole(props.row.id, 'security_auditor').then(refresh)"
                      />
                      <menu-item
                        label="Revoke platform admin"
                        @click="identityClient.revokeRole(props.row.id, 'platform_admin').then(refresh)"
                      />
                      <menu-item
                        label="Revoke security auditor"
                        @click="identityClient.revokeRole(props.row.id, 'security_auditor').then(refresh)"
                      />
                    </template>
                    <menu-item
                      :label="t('Delete User')"
                      @click="deleteUser(props.row)"
                      hover:text-err
                    />
                  </q-list>
                </q-menu>
              </q-btn>
            </template>
          </q-td>
        </template>
      </q-table>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import type { QTableColumn, QTableProps } from 'quasar'
import { useQuasar } from 'quasar'
import { identityClient, session } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import { computed, onMounted, ref, watch } from 'vue'
import UpdateUserDialog from '../components/UpdateUserDialog.vue'
import MenuItem from 'src/components/MenuItem.vue'
import BanUserDialog from '../components/BanUserDialog.vue'
import CreateUserDialog from '../components/CreateUserDialog.vue'
import type { components } from 'src/api/generated/schema'

type UserWithRole = components['schemas']['IdentityUser']

const columns: QTableColumn[] = [
  { name: 'id', label: t('ID'), field: 'id', sortable: true, align: 'left' },
  { name: 'name', label: t('Name'), field: 'displayName', sortable: true },
  { name: 'email', label: t('Email'), field: 'email', sortable: true },
  { name: 'roles', label: t('Roles'), field: row => row.platformRoles.join(', '), sortable: true },
  { name: 'actions', label: t('Actions'), field: () => null },
]

const rows = ref<UserWithRole[]>([])
const searchValue = ref('')
const searchField = ref<('email' | 'name')>('email')
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
      message: t('Failed to fetch users: {0}', error.message),
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
    title: t('Reset Password'),
    message: t('Set new password for user "{0}":', displayName),
    prompt: {
      model: '',
      type: 'password',
    },
    cancel: true,
  }).onOk(newPassword => {
    identityClient.setPassword(id, newPassword).catch(err => {
      console.error(err)
      $q.notify({
        message: t('Failed to reset password: {0}', err.message),
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
    title: t('Revoke Sessions'),
    message: t('Are you sure you want to revoke all sessions for "{0}"?', displayName),
    cancel: true,
    ok: t('Revoke'),
  }).onOk(() => {
    identityClient.revokeSessions(id).catch(err => {
      console.error(err)
      $q.notify({
        message: t('Failed to revoke sessions: {0}', err.message),
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
    title: t('Delete User'),
    message: t('Are you sure you want to delete user "{0}"? Note that you must delete all knowledge bases created by this user before you can delete the user.', displayName),
    cancel: true,
    ok: {
      label: t('Delete'),
      color: 'negative',
      flat: true,
    },
  }).onOk(() => {
    identityClient.deleteUser(id).then(refresh).catch(err => {
      console.error(err)
      $q.notify({
        message: t('Failed to delete user: {0}', err.message),
        color: 'negative',
      })
    })
  })
}
</script>
<style lang="scss">
.users-table {
  th:last-child,
  td:last-child {
    --at-apply: 'pos-sticky right-0 z-1 bg-sur-c-low';
  }
}
</style>
