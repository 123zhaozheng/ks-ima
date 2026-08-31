<template>
  <div class="kb-manage-section">
    <div class="kb-manage-section-title">
      {{ t('Share links') }}
    </div>
    <div class="tk-caption">
      {{ t('Anyone with a share link can join this knowledge base.') }}
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
          { label: t('Read only'), value: 'viewer' },
          { label: t('Editable'), value: 'editor' },
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
        :label="t('Expires in (days)')"
        :hint="t('Leave empty for no expiry.')"
      />
      <q-btn
        dense
        no-caps
        unelevated
        color="primary"
        icon="sym_o_link"
        :label="t('Create share link')"
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
        :label="t('Copy link')"
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
            {{ link.role === 'editor' ? t('Editable') : t('Read only') }}
            <q-badge
              v-if="linkState(link) !== 'active'"
              outline
              color="grey-7"
              class="kb-share-state"
            >
              {{ linkState(link) === 'revoked' ? t('Revoked') : t('Expired') }}
            </q-badge>
          </q-item-label>
          <q-item-label caption>
            {{ t('Created {0}', formatDate(link.createdAt)) }} ·
            {{ link.expiresAt ? t('Expires {0}', formatDate(link.expiresAt)) : t('Never expires') }}
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
            :title="t('Revoke link')"
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
      {{ t('No share links yet') }}
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
import { t } from 'src/utils/i18n'

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
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Create failed') })
      return
    }
    justCreated.value = result.data
    Notify.create({ type: 'positive', message: t('Share link created') })
    invalidateLinks()
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
  } finally {
    creating.value = false
  }
}

async function copy(url: string) {
  try {
    await copyToClipboard(url)
    Notify.create({ type: 'positive', message: t('Copied') })
  } catch {
    Notify.create({ type: 'negative', message: t('Copy failed') })
  }
}

function confirmRevoke(link: ShareLink) {
  $q.dialog({
    title: t('Revoke link'),
    message: t('Revoking stops new members from joining with this link. Members who already joined are not affected.'),
    cancel: true,
    ok: {
      label: t('Revoke'),
      color: 'negative',
      flat: true,
    },
  }).onOk(async () => {
    const result = await identityClient.revokeKbShareLink(props.kbId, link.id)
    if (result.error) {
      Notify.create({ type: 'negative', message: apiErrorMessage(result.error, 'Revoke failed') })
      return
    }
    if (justCreated.value?.id === link.id) justCreated.value = null
    Notify.create({ type: 'positive', message: t('Link revoked') })
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
