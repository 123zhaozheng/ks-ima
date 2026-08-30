<template>
  <q-header class="tk-header">
    <q-toolbar>
      <q-btn
        flat
        dense
        round
        icon="sym_o_menu"
        @click="uiStateStore.toggleMainDrawer"
      />
      <q-toolbar-title>{{ t('Tags') }}</q-toolbar-title>
      <q-btn
        unelevated
        no-caps
        color="primary"
        icon="sym_o_add"
        :label="t('New tag')"
        @click="create"
      />
    </q-toolbar>
  </q-header>
  <q-page-container>
    <q-page class="tk-page tags-page">
      <section class="tk-card tags-card">
        <q-list separator>
          <q-item
            v-for="tag in tags"
            :key="String(tag.id)"
          >
            <q-item-section>
              <q-item-label>{{ tag.name }}</q-item-label>
              <q-item-label caption>
                {{ t('{0} documents', tag.count) }}
              </q-item-label>
            </q-item-section>
            <q-item-section side>
              <div class="tags-actions">
                <q-btn
                  flat
                  dense
                  round
                  icon="sym_o_edit"
                  :title="t('Rename')"
                  @click="rename(tag)"
                />
                <q-btn
                  flat
                  dense
                  round
                  icon="sym_o_merge"
                  :title="t('Merge')"
                  @click="merge(tag)"
                />
                <q-btn
                  flat
                  dense
                  round
                  icon="sym_o_delete"
                  :title="t('Delete')"
                  @click="remove(tag)"
                />
              </div>
            </q-item-section>
          </q-item>
          <q-item v-if="!loading && !tags.length">
            <q-item-section class="tags-empty">
              {{ t('No tags') }}
            </q-item-section>
          </q-item>
        </q-list>
        <q-inner-loading :showing="loading" />
      </section>
    </q-page>
  </q-page-container>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useQuasar } from 'quasar'
import { knowledgeClient } from 'src/api/knowledge-client'
import { useWorkspaceStore } from 'src/stores/workspace'
import { useUiStateStore } from 'src/stores/ui-state'
import { useKnowledgeMutations, useKnowledgeTags } from 'src/composables/use-knowledge'
import { t } from 'src/utils/i18n'
import type { components } from 'src/api/generated/schema'

type Tag = components['schemas']['TagResponse']
const workspace = useWorkspaceStore()
const uiStateStore = useUiStateStore()
const $q = useQuasar()
const tagsQuery = useKnowledgeTags(() => workspace.id)
const tagMutations = useKnowledgeMutations()
const tags = computed<Tag[]>(() => tagsQuery.data.value ?? [])
const loading = computed(() => tagsQuery.isFetching.value)
function create() {
  if (!workspace.id) return
  $q.dialog({ title: t('New tag'), prompt: { model: '', type: 'text' }, cancel: true }).onOk(async (name: string) => {
    await knowledgeClient.createTag(workspace.id!, { name })
    await tagsQuery.refetch()
  })
}
function rename(tag: Tag) {
  if (!workspace.id) return
  $q.dialog({ title: t('Rename tag'), prompt: { model: tag.name, type: 'text' }, cancel: true }).onOk(async (name: string) => {
    await knowledgeClient.updateTag(workspace.id!, String(tag.id), { name, expectedVersion: tag.version })
    await tagsQuery.refetch()
  })
}
function remove(tag: Tag) {
  if (!workspace.id) return
  $q.dialog({ title: t('Delete tag'), message: t('Delete {0}?', tag.name), cancel: true }).onOk(async () => {
    await tagMutations.deleteTag.mutateAsync({ workspaceId: workspace.id!, tagId: String(tag.id), expectedVersion: tag.version })
    await tagsQuery.refetch()
  })
}
function merge(tag: Tag) {
  if (!workspace.id) return
  const choices = tags.value.filter(candidate => candidate.id !== tag.id)
  $q.dialog({
    title: t('Merge tag'),
    message: t('Enter the tag name to keep'),
    prompt: { model: '', type: 'text' },
    cancel: true,
  }).onOk(async (name: string) => {
    const target = choices.find(candidate => candidate.name === name)
    if (!target) return
    await tagMutations.mergeTag.mutateAsync({
      workspaceId: workspace.id!,
      tagId: String(tag.id),
      targetTagId: String(target.id),
      expectedVersion: tag.version,
      expectedTargetVersion: target.version,
    })
    await tagsQuery.refetch()
  })
}
</script>

<style scoped>
.tags-card {
  position: relative;
}

.tags-actions {
  display: flex;
  gap: var(--tk-space-1);
}

.tags-empty {
  color: var(--tk-text-secondary);
}
</style>
