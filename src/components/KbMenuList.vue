<template>
  <q-list min-w="260px">
    <div
      flex
      text-on-sur-var
      items-center
      py-2
      pl-4
      pr-1
    >
      <div>
        {{ t('Knowledge bases') }}
      </div>
      <q-btn
        icon="sym_o_add"
        :title="t('Add knowledge base')"
        flat
        round
        size="sm"
        ml-a
        data-testid="kb-add"
      >
        <q-menu>
          <q-list>
            <menu-item
              v-close-popup
              :label="t('Create knowledge base')"
              icon="sym_o_add_box"
              data-testid="kb-create-entry"
              @click="showCreate = true"
            />
            <menu-item
              v-close-popup
              :label="t('Join with a link')"
              icon="sym_o_link"
              data-testid="kb-join-entry"
              @click="joinWithLink"
            />
          </q-list>
        </q-menu>
      </q-btn>
    </div>
    <dense-item
      v-for="item in kbs"
      :key="item.id"
      :avatar="kbAvatar(item)"
      :label="item.name"
      :active="item.id === kbStore.id"
      clickable
      data-testid="kb-switch-item"
      @click="kbStore.switchKb(item.id)"
      v-close-popup
    >
      <q-item-section side>
        <q-badge
          outline
          color="primary"
          class="kb-role-badge"
        >
          {{ item.owned ? t('Created by me') : t('Shared with me') }}
        </q-badge>
      </q-item-section>
    </dense-item>
    <q-item
      v-if="!kbs.length"
      data-testid="kb-empty"
    >
      <q-item-section class="text-secondary">
        {{ t('No knowledge bases yet') }}
      </q-item-section>
    </q-item>
    <q-separator spaced />
    <menu-item
      :label="t('Create knowledge base')"
      icon="sym_o_add_box"
      data-testid="kb-create-bottom"
      @click="showCreate = true"
    />
    <menu-item
      :label="t('Join with a link')"
      icon="sym_o_link"
      data-testid="kb-join-bottom"
      @click="joinWithLink"
    />

    <q-dialog
      v-model="showCreate"
      @hide="name = ''"
    >
      <q-card min-w="360px">
        <q-card-section class="text-h6">
          {{ t('Create knowledge base') }}
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="name"
            outlined
            autofocus
            :label="t('Knowledge base name')"
            data-testid="kb-name-input"
            @keyup.enter="create"
          />
          <div class="tk-caption q-mt-sm">
            {{ t('You will become the owner of the new knowledge base.') }}
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            :label="t('Cancel')"
          />
          <q-btn
            flat
            color="primary"
            :label="t('Create')"
            :loading="creating"
            :disable="!name.trim()"
            data-testid="kb-create-button"
            @click="create"
          />
        </q-card-actions>
      </q-card>
    </q-dialog>
  </q-list>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Notify, useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { useQueryClient } from '@tanstack/vue-query'
import DenseItem from './DenseItem.vue'
import MenuItem from './MenuItem.vue'
import { kbAvatar } from 'src/utils/defaults'
import { useKbStore } from 'src/stores/knowledge-base'
import { identityClient } from 'src/utils/identity-client'
import { apiErrorMessage } from 'src/utils/api-error'
import { t } from 'src/utils/i18n'

const kbStore = useKbStore()
const $q = useQuasar()
const router = useRouter()
const queryClient = useQueryClient()

const kbs = computed(() => kbStore.kbs ?? [])
const showCreate = ref(false)
const name = ref('')
const creating = ref(false)

async function create() {
  const kbName = name.value.trim()
  if (!kbName || creating.value) return
  creating.value = true
  try {
    const { data, error } = await identityClient.createKnowledgeBase({ name: kbName })
    if (error || !data) {
      Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
      return
    }
    Notify.create({ type: 'positive', message: t('Knowledge base created') })
    showCreate.value = false
    // Membership list drives the switcher; refresh then select the new kb.
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.switchKb(data.id)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, 'Create failed') })
  } finally {
    creating.value = false
  }
}

function joinWithLink() {
  $q.dialog({
    title: t('Join knowledge base'),
    prompt: {
      model: '',
      label: t('Share link'),
    },
    cancel: true,
  }).onOk((link: string) => {
    const token = link.match(/\/join\/(.+)/)?.[1] ?? link.trim()
    token && router.push(`/join/${encodeURIComponent(token)}`)
  })
}
</script>

<style scoped>
.kb-role-badge {
  font-weight: 400;
}
</style>
