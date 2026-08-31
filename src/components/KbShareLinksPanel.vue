<template>
  <div class="kb-manage-section">
    <div class="kb-manage-section-title">
      分享链接
    </div>
    <div class="tk-caption">
      拿到分享链接的人都可以加入该知识库。
    </div>
    <div class="kb-share-create">
      <q-btn-toggle
        v-model="role"
        dense
        no-caps
        unelevated
        toggle-color="primary"
        color="grey-3"
        text-color="grey-8"
        :options="[
          { label: '只读', value: 'viewer' },
          { label: '可编辑', value: 'editor' },
        ]"
        data-testid="share-role-toggle"
      />
      <q-input
        v-model.number="expiresInDays"
        dense
        outlined
        type="number"
        min="1"
        class="kb-share-expiry"
        label="有效期（天）"
        hint="留空表示不过期。"
      />
      <q-btn
        dense
        no-caps
        unelevated
        color="primary"
        icon="sym_o_link"
        label="创建分享链接"
        :loading="creating"
        data-testid="share-link-create"
        @click="create"
      />
    </div>
    <div
      v-if="justCreated?.url"
      class="kb-share-new"
      data-testid="share-link-new"
    >
      <q-input
        :model-value="justCreated.url"
        dense
        borderless
        readonly
        class="kb-share-new-url"
        data-testid="share-link-url"
      />
      <q-btn
        dense
        flat
        no-caps
        icon="sym_o_content_copy"
        label="复制链接"
        data-testid="share-link-copy"
        @click="copy(justCreated.url!)"
      />
    </div>
    <q-list
      v-if="links.length"
      dense
      class="kb-share-list"
    >
      <q-item
        v-for="link in links"
        :key="link.id"
        class="kb-share-row"
      >
        <q-item-section
          avatar
          min-w-0
        >
          <q-icon :name="linkState(link) === 'active' ? 'sym_o_link' : 'sym_o_link_off'" />
        </q-item-section>
        <q-item-section>
          <q-item-label>
            {{ link.role === 'editor' ? '可编辑' : '只读' }}
            <q-badge
              v-if="linkState(link) !== 'active'"
              outline
              color="grey-7"
              class="kb-share-state"
            >
              {{ linkState(link) === 'revoked' ? '已撤销' : '已过期' }}
            </q-badge>
          </q-item-label>
          <q-item-label caption>
            创建于 {{ formatDate(link.createdAt) }} ·
            {{ link.expiresAt ? `过期于 ${formatDate(link.expiresAt)}` : '永不过期' }}
          </q-item-label>
        </q-item-section>
        <q-item-section
          v-if="linkState(link) === 'active'"
          side
        >
          <q-btn
            flat
            dense
            round
            size="sm"
            icon="sym_o_block"
            color="negative"
            title="撤销链接"
            data-testid="share-link-revoke"
            @click="confirmRevoke(link)"
          />
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
      还没有分享链接
    </div>
  </div>
</template>

<script setup lang="ts">
import type { components } from 'src/api/generated/schema'
import { computed, ref } from 'vue'
import { Notify, copyToClipboard, useQuasar } from 'quasar'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { apiErrorMessage } from 'src/utils/api-error'
import { identityClient } from 'src/utils/identity-client'

type ShareLink = components['schemas']['ShareLink']

const props = defineProps<{
  kbId: string
}>()

const $q = useQuasar()
const queryClient = useQueryClient()

const role = ref<'editor' | 'viewer'>('viewer')
const expiresInDays = ref<number | null>(null)
const creating = ref(false)
const justCreated = ref<ShareLink | null>(null)

const query = useQuery({
  queryKey: computed(() => ['kb-share-links', props.kbId] as const),
  queryFn: async () => {
    const result = await identityClient.listKbShareLinks(props.kbId)
    if (result.error) throw new Error(result.error.message)
    return result.data!
  },
  enabled: computed(() => Boolean(props.kbId)),
})
const links = computed(() => query.data.value ?? [])

function invalidateLinks() {
  queryClient.invalidateQueries({ queryKey: ['kb-share-links', props.kbId] })
}

function linkState(link: ShareLink): 'active' | 'revoked' | 'expired' {
  if (link.revokedAt) return 'revoked'
  if (link.expiresAt && new Date(link.expiresAt).getTime() < Date.now()) return 'expired'
  return 'active'
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString()
}

async function create() {
  if (creating.value) return
  creating.value = true
  try {
    const days = typeof expiresInDays.value === 'number' && expiresInDays.value > 0 ? Math.floor(expiresInDays.value) : null
    const result = await identityClient.createKbShareLink(props.kbId, { role: role.value, expiresInDays: days })
    if (result.error || !result.data) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '创建失败') })
      return
    }
    justCreated.value = result.data
    Notify.create({ type: 'positive', message: '分享链接已创建' })
    invalidateLinks()
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
  } finally {
    creating.value = false
  }
}

async function copy(url: string) {
  try {
    await copyToClipboard(url)
    Notify.create({ type: 'positive', message: '已复制' })
  } catch {
    Notify.create({ type: 'negative', message: '复制失败' })
  }
}

function confirmRevoke(link: ShareLink) {
  $q.dialog({
    title: '撤销链接',
    message: '撤销后，此链接将无法再用于加入。已加入的成员不受影响。',
    cancel: true,
    ok: {
      label: '撤销',
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.revokeKbShareLink(props.kbId, link.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, '撤销失败') })
      return
    }
    if (justCreated.value?.id === link.id) justCreated.value = null
    Notify.create({ type: 'positive', message: '链接已撤销' })
    invalidateLinks()
  })
}
</script>

<style scoped>
.kb-share-create {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--tk-space-2);
  margin-top: var(--tk-space-2);
}

.kb-share-expiry {
  width: 150px;
}

.kb-share-new {
  display: flex;
  align-items: center;
  gap: var(--tk-space-1);
  margin-top: var(--tk-space-2);
  padding: var(--tk-space-1) var(--tk-space-2);
  border: 1px solid var(--tk-accent);
  border-radius: var(--tk-radius);
  background-color: var(--tk-accent-soft);
}

.kb-share-new-url {
  flex: 1;
  min-width: 0;
}

.kb-share-state {
  font-weight: 400;
  margin-left: var(--tk-space-1);
}

.kb-share-row {
  border-radius: var(--tk-radius);
}
</style>
