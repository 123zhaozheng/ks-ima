<template>
  <div class="kb-manage-section">
    <div class="kb-manage-section-title">
      {{ t('Members') }}
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
            >（{{ t('You') }}）</span>
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
              :aria-label="t('More')"
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
                    <q-item-section>{{ t('Make editor') }}</q-item-section>
                  </q-item>
                  <q-item
                    v-if="member.role === 'editor'"
                    v-close-popup
                    clickable
                    @click="changeRole(member, 'viewer')"
                  >
                    <q-item-section>{{ t('Make viewer') }}</q-item-section>
                  </q-item>
                  <q-separator />
                  <q-item
                    v-close-popup
                    clickable
                    class="text-negative"
                    @click="confirmRemove(member)"
                  >
                    <q-item-section>{{ t('Remove member') }}</q-item-section>
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
      {{ t('No members') }}
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
        :label="t('Leave knowledge base')"
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
import { t } from 'src/utils/i18n'

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
  if (role === 'owner') return t('Owner')
  if (role === 'editor') return t('Editor')
  return t('Viewer')
}

async function changeRole(member: KbMember, role: 'editor' | 'viewer') {
  const result = await identityClient.updateKbMemberRole(props.kbId, member.userId, { role, expectedVersion: member.version })
  if (result.error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Update failed') })
    return
  }
  Notify.create({ type: 'positive', message: t('Role updated') })
  invalidateMembers()
}

function confirmRemove(member: KbMember) {
  $q.dialog({
    title: t('Remove member'),
    message: t('Are you sure you want to remove "{0}" from this knowledge base?', displayName(member)),
    cancel: true,
    ok: {
      label: t('Remove'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.removeKbMember(props.kbId, member.userId, member.version)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Remove failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Member removed') })
    invalidateMembers()
  })
}

function confirmLeave() {
  $q.dialog({
    title: t('Leave knowledge base'),
    message: t('After leaving, you will lose access to this knowledge base. You can rejoin with a new share link.'),
    cancel: true,
    ok: {
      label: t('Leave'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.leaveKnowledgeBase(props.kbId)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Leave failed') })
      return
    }
    // Membership is gone; refresh the switcher list and let the store fall
    // back to the next knowledge base.
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.id = null
    emit('left')
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
