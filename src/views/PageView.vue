<template>
  <div
    view-styles
    flex="~ col"
  >
    <common-toolbar>
      <div
        px-2
        min-w-0
        grow
      >
        <page-title-input
          :model-value="page.entity?.name ?? ''"
          @update:model-value="updateTitle"
          :readonly="readonlyStateStore.readonly"
          w-full
        />
      </div>
      <q-btn
        icon="sym_o_chat_add_on"
        :title="t('Open AI Chat')"
        flat
        dense
        round
        @click="createChat"
        text-on-sur-var
      />
    </common-toolbar>
    <md-editor
      v-model="text"
      :theme="dark ? 'dark' : 'light'"
      :preview="false"
      :toolbars="toolbars"
      :readonly="readonlyStateStore.readonly"
      @on-change="onChange"
      class="note-editor"
      grow
    />
  </div>
</template>

<script setup lang="ts">
import type { FullPage } from 'app/src-shared/queries'
import { mutate } from 'src/utils/zero-session'
import { mutators } from 'app/src-shared/mutators'
import { genId } from 'app/src-shared/utils/id'
import { useQuasar } from 'quasar'
import { useRouter } from 'vue-router'
import { inject, ref, watch, type Ref } from 'vue'
import { t } from 'src/utils/i18n'
import { useReadonlyStateStore } from 'src/stores/readonly-state'
import PageTitleInput from 'src/components/PageTitleInput.vue'
import type { LayoutPosition } from 'src/utils/types'
import { MdEditor } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'

const props = defineProps<{
  page: FullPage
}>()

const position = inject<Ref<LayoutPosition>>('position')!
const readonlyStateStore = useReadonlyStateStore()
const $q = useQuasar()
const dark = $q.dark.isActive
const router = useRouter()
const text = ref(props.page.text ?? '')
const toolbars = ['bold', 'underline', 'italic', 'strikeThrough', 'title', 'quote', 'unorderedList', 'orderedList', 'codeRow', 'code', 'link', 'table', 'revoke', 'next', 'save'] as const

watch(() => props.page.id, () => {
  text.value = props.page.text ?? ''
})

let timer: number | undefined
function onChange(value: string) {
  text.value = value
  window.clearTimeout(timer)
  timer = window.setTimeout(() => {
    if (readonlyStateStore.readonly) return
    mutate(mutators.updatePage({ id: props.page.id, text: value }))
  }, 600)
}

function updateTitle(name: string) {
  mutate(mutators.updateEntity({ id: props.page.id, name }))
}

async function createChat() {
  const id = genId()
  await mutate(mutators.createChat({
    ids: [id, genId()],
    parentId: props.page.entity?.parentId ?? props.page.id,
    name: props.page.entity?.name,
  })).client
  const query = position.value === 'right' ? { rightEntity: JSON.stringify({ type: 'chat', id }) } : {}
  router.push({ path: `/chat/${id}`, query })
}
</script>

<style>
.note-editor {
  height: 100%;
  border: none;
}
.note-editor .md-editor {
  height: 100%;
}
</style>
