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
        知识库
      </div>
      <q-btn
        icon="sym_o_add"
        title="添加知识库"
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
              label="新建知识库"
              icon="sym_o_add_box"
              data-testid="kb-create-entry"
              @click="showCreate = true"
            />
            <menu-item
              v-close-popup
              label="通过链接加入"
              icon="sym_o_link"
              data-testid="kb-join-entry"
              @click="joinWithLink"
            />
          </q-list>
        </q-menu>
      </q-btn>
    </div>
    <template
      v-for="item in kbs"
      :key="item.id"
    >
      <dense-item
        :avatar="kbAvatar(item)"
        :label="item.name"
        :active="item.id === kbStore.id"
        clickable
        data-testid="kb-switch-item"
        v-close-popup
        @click="kbStore.switchKb(item.id)"
      >
        <q-item-section side>
          <div
            flex
            items-center
            gap-1
          >
            <q-icon
              v-if="item.id === kbStore.id"
              name="sym_o_check"
              color="primary"
              size="16px"
              data-testid="kb-switch-item-check"
            />
            <q-badge
              outline
              color="primary"
              class="kb-role-badge"
            >
              {{ item.owned ? '我创建的' : '共享给我的' }}
            </q-badge>
          </div>
        </q-item-section>
      </dense-item>
      <q-item
        v-if="item.id === kbStore.id"
        v-close-popup
        clickable
        dense
        class="kb-manage-entry"
        data-testid="kb-manage-entry"
        @click="kbStore.openManage()"
      >
        <q-item-section
          avatar
          min-w-0
        >
          <q-icon
            name="sym_o_tune"
            size="18px"
          />
        </q-item-section>
        <q-item-section>
          管理与分享
        </q-item-section>
      </q-item>
    </template>
    <q-item
      v-if="!kbs.length"
      data-testid="kb-empty"
    >
      <q-item-section class="text-secondary">
        还没有知识库
      </q-item-section>
    </q-item>
    <q-separator spaced />
    <menu-item
      label="新建知识库"
      icon="sym_o_add_box"
      data-testid="kb-create-bottom"
      @click="showCreate = true"
    />
    <menu-item
      label="通过链接加入"
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
          新建知识库
        </q-card-section>
        <q-card-section>
          <q-input
            v-model="name"
            outlined
            autofocus
            label="知识库名称"
            data-testid="kb-name-input"
            @keyup.enter="create"
          />
          <div class="tk-caption q-mt-sm">
            你将成为新知识库的所有者。
          </div>
        </q-card-section>
        <q-card-actions align="right">
          <q-btn
            v-close-popup
            flat
            label="取消"
          />
          <q-btn
            flat
            color="primary"
            label="创建"
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
      Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
      return
    }
    Notify.create({ type: 'positive', message: '知识库已创建' })
    showCreate.value = false
    // Membership list drives the switcher; refresh then select the new kb.
    await queryClient.invalidateQueries({ queryKey: ['knowledge-bases', 'member'] })
    kbStore.switchKb(data.id)
  } catch (error) {
    Notify.create({ type: 'negative', message: apiErrorMessage(error, '创建失败') })
  } finally {
    creating.value = false
  }
}

function joinWithLink() {
  $q.dialog({
    title: '加入知识库',
    prompt: {
      model: '',
      label: '分享链接',
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

.kb-manage-entry {
  min-height: 32px;
  font-size: 13px;
  color: var(--tk-text-secondary);
}
</style>
