<template>
  <div class="kb-manage-section">
    <div class="kb-manage-section-title">
      成员
    </div>
    <q-list
      v-if="members.length"
      dense
      class="kb-member-list"
    >
      <q-item
        v-for="member in members"
        :key="member.userId"
        class="kb-member-row"
      >
        <q-item-section
          avatar
          min-w-0
        >
          <q-avatar
            size="28px"
            font-size="13px"
            color="grey-4"
            text-color="grey-8"
          >
            {{ initial(member) }}
          </q-avatar>
        </q-item-section>
        <q-item-section>
          <q-item-label
            text-ellipsis
            whitespace-nowrap
            overflow-hidden
          >
            {{ displayName(member) }}
            <span
              v-if="member.userId === userId"
              class="tk-caption"
            >（你）</span>
          </q-item-label>
          <q-item-label
            v-if="member.email"
            caption
            text-ellipsis
            whitespace-nowrap
            overflow-hidden
          >
            {{ member.email }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div
            flex
            items-center
            gap-1
          >
            <q-badge
              outline
              :color="member.role === 'owner' ? 'primary' : 'grey-7'"
              class="kb-role-badge"
            >
              {{ roleLabel(member.role) }}
            </q-badge>
            <q-btn
              v-if="isOwner && member.userId !== userId"
              flat
              dense
              round
              size="sm"
              icon="sym_o_more_vert"
              aria-label="更多"
              data-testid="kb-member-menu"
            >
              <q-menu>
                <q-list dense>
                  <q-item
                    v-if="member.role === 'viewer'"
                    v-close-popup
                    clickable
                    @click="changeRole(member, 'editor')"
                  >
                    <q-item-section>设为可编辑</q-item-section>
                  </q-item>
                  <q-item
                    v-if="member.role === 'editor'"
                    v-close-popup
                    clickable
                    @click="changeRole(member, 'viewer')"
                  >
                    <q-item-section>设为只读</q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item
                    v-close-popup
                    clickable
                    class="text-negative"
                    @click="confirmRemove(member)"
                  >
                    <q-item-section>移除成员</q-item-section>
                  </q-item>
                </q-list>
              </q-menu>
            </q-btn>
          </div>
        </q-item-section>
      </q-item>
    </q-list>
    <div
      v-else-if="query.isLoading.value"
      class="kb-manage-loading"
    >
      <q-spinner
        size="20px"
        color="primary"
      />
    </div>
    <div
      v-else
      class="kb-manage-empty"
    >
      暂无成员
    </div>
    <div
      v-if="!isOwner && userId"
      class="kb-manage-footer"
    >
      <q-btn
        flat
        dense
        no-caps
        icon="sym_o_logout"
        color="negative"
        label="退出知识库"
        data-testid="kb-leave"
        @click="confirmLeave"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { useKbStore } from 'src/stores/knowledge-base'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient, session } from 'src/utils/identity-client'

type KbMember = components['schemas']['KbMember']

const props = defineProps<{
  kbId: string
  isOwner: boolean
}>()

const emit = defineEmits<{
  left: []
}>()

const $q = useQuasar()
const queryClient = useQueryClient()
const kbStore = useKbStore()
const userId = computed(() => session.value.data?.user.id ?? null)

const query = useQuery({
  queryKey: computed(() => ['kb-members', props.kbId] as const),
  queryFn: async () => {
    const result = await identityClient.listKbMembers(props.kbId)
    if (result.error) throw new Error(result.error.message)
    return result.data!
  },
  enabled: computed(() => Boolean(props.kbId)),
})
const members = computed(() => query.data.value ?? [])

function invalidateMembers() {
  queryClient.invalidateQueries({ queryKey: ['kb-members', props.kbId] })
}

function displayName(member: KbMember) {
  return member.displayName || member.email || member.userId
}

function initial(member: KbMember) {
  return (displayName(member)[0] ?? '?').toUpperCase()
}

function roleLabel(role: KbMember['role']) {
  if (role === 'owner') return '所有者'
  if (role === 'editor') return '编辑者'
  return '浏览者'
}

async function changeRole(member: KbMember, role: 'editor' | 'viewer') {
  const result = await identityClient.updateKbMemberRole(props.kbId, member.userId, { role, expectedVersion: member.version })
  if (result.error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '更新失败') })
    return
  }
  Notify.create({ type: 'positive', message: '角色已更新' })
  invalidateMembers()
}

function confirmRemove(member: KbMember) {
  $q.dialog({
    title: '移除成员',
    message: `确定将“${displayName(member)}”移出该知识库吗？`,
    cancel: true,
    ok: {
      label: '移除',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.removeKbMember(props.kbId, member.userId, member.version)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '移除失败') })
      return
    }
    Notify.create({ type: 'positive', message: '成员已移除' })
    invalidateMembers()
  })
}

function confirmLeave() {
  $q.dialog({
    title: '退出知识库',
    message: '退出后，你将无法再访问该知识库。之后可通过新的分享链接重新加入。',
    cancel: true,
    ok: {
      label: '离开',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.leaveKnowledgeBase(props.kbId)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '退出失败') })
      return
    }
    // Membership is gone. Clear the selection before the refreshed list
    // lands so the store falls back to the next knowledge base.
    kbStore.id = null
    emit('left')
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
  })
}
</script>

<style scoped>
.kb-member-row {
  border-radius: var(--tk-radius);
}

.kb-role-badge {
  font-weight: 400;
}
</style>
