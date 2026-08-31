<template>
  <q-drawer
    show-if-above
    bg-sur-c
    flex="~ col"
    p-2
  >
    <q-list>
      <q-item
        v-if="canManageUsers"
        to="/users"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_group" />
        </q-item-section>
        <q-item-section>
          用户
        </q-item-section>
      </q-item>
      <q-item
        to="/knowledge-bases"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_deployed_code" />
        </q-item-section>
        <q-item-section>
          知识库
        </q-item-section>
      </q-item>
      <q-item
        v-if="canReadModelGovernance"
        to="/models"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_neurology" />
        </q-item-section>
        <q-item-section>
          模型配置
        </q-item-section>
      </q-item>
      <q-item
        to="/audit"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_history" />
        </q-item-section>
        <q-item-section>审计</q-item-section>
      </q-item>
      <q-item
        v-if="canManageSettings"
        clickable
        @click="openSettings"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_settings" />
        </q-item-section>
        <q-item-section>
          设置
        </q-item-section>
      </q-item>
    </q-list>
    <q-list mt-a>
      <q-item
        clickable
        @click="signOut"
        item-rd
      >
        <q-item-section avatar>
          <q-icon name="sym_o_logout" />
        </q-item-section>
        <q-item-section>
          退出登录
        </q-item-section>
      </q-item>
    </q-list>
  </q-drawer>
</template>

<script setup lang="ts">
import { useQuasar } from 'quasar'
import { identityClient, session } from 'src/utils/identity-client'
import { useRouter } from 'vue-router'
import UpdateSettingsDialog from './UpdateSettingsDialog.vue'
import { computed } from 'vue'

const canManageUsers = computed(() => session.value.data?.user.platformRoles.includes('super_admin') || session.value.data?.user.platformRoles.includes('platform_admin'))
const canManageSettings = canManageUsers
const canReadModelGovernance = computed(() => canManageUsers.value || session.value.data?.user.platformRoles.includes('security_auditor'))

const router = useRouter()
function signOut() {
  identityClient.signOut()
  router.push('/auth/sign-in')
}

const $q = useQuasar()
function openSettings() {
  $q.dialog({
    component: UpdateSettingsDialog,
  })
}
</script>
