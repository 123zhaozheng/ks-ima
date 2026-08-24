<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(94vw, 560px)">
      <q-card-section class="row items-center">
        <div class="text-h6">
          {{ t('Folder permissions') }}
        </div>
        <q-space />
        <q-btn
          flat
          round
          icon="close"
          :title="t('Close')"
          @click="onDialogCancel"
        />
      </q-card-section>
      <q-card-section>
        <q-banner
          v-if="error"
          class="bg-red-1 text-red-9 q-mb-md"
        >
          {{ error }}
        </q-banner>
        <q-spinner
          v-if="loading"
          color="primary"
        />
        <template v-else>
          <q-toggle
            v-model="inherit"
            :disable="entity.id === entity.rootId"
            :label="t('Inherit from parent')"
          />
          <div
            v-if="acl"
            class="text-caption text-grey-7 q-mb-md"
          >
            {{ t('Effective source') }}: {{ acl.effectiveSource }}
          </div>
          <q-select
            v-if="!inherit"
            v-model="selectedSubjectKey"
            dense
            outlined
            emit-value
            map-options
            :options="subjectOptions"
            :label="t('ACL subject')"
            class="q-mb-md"
          />
          <q-option-group
            v-if="!inherit"
            v-model="selectedActions"
            type="checkbox"
            :options="actionOptions"
          />
          <q-btn
            v-if="!inherit && selectedSubjectKey"
            flat
            color="negative"
            icon="remove_circle_outline"
            :label="t('Remove subject grants')"
            @click="removeSubject"
          />
        </template>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          :label="t('Cancel')"
          @click="onDialogCancel"
        />
        <q-btn
          color="primary"
          unelevated
          :loading="saving"
          :label="t('Save')"
          :disable="loading || !!error"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useDialogPluginComponent } from 'quasar'
import { identityClient } from 'src/utils/identity-client'
import { t } from 'src/utils/i18n'
import type { components } from 'src/api/generated/schema'

const props = defineProps<{ entity: { id: string, rootId: string } }>()
defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
type Acl = components['schemas']['FolderAcl']
type Action = components['schemas']['AclEntry']['action']
type AclSubject = components['schemas']['AclSubject']
const acl = ref<Acl>()
const inherit = ref(true)
const subjects = ref<AclSubject[]>([])
const selectedSubjectKey = ref('')
const subjectEntries = ref<Record<string, Action[]>>({})
const selectedActions = ref<Action[]>(['view_metadata', 'view_content', 'download', 'ask'])
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const actionOptions = [
  { label: t('View metadata'), value: 'view_metadata' },
  { label: t('View content'), value: 'view_content' },
  { label: t('Download'), value: 'download' },
  { label: t('Ask'), value: 'ask' },
  { label: t('Create child'), value: 'create_child' },
  { label: t('Edit'), value: 'edit' },
  { label: t('Move'), value: 'move' },
  { label: t('Delete'), value: 'delete' },
  { label: t('Manage ACL'), value: 'manage_acl' },
]
const subjectOptions = computed(() => subjects.value.map(subject => ({
  label: subject.email ? `${subject.label} (${subject.email})` : subject.label,
  value: `${subject.subjectType}:${subject.subjectId}`,
})))
function selectSubject(key: string) {
  selectedSubjectKey.value = key
  selectedActions.value = [...(subjectEntries.value[key] ?? [])]
}
function removeSubject() {
  if (!selectedSubjectKey.value) return
  delete subjectEntries.value[selectedSubjectKey.value]
  selectedActions.value = []
}
watch(selectedSubjectKey, key => {
  if (key) selectedActions.value = [...(subjectEntries.value[key] ?? [])]
})
async function load() {
  const [result, subjectResult] = await Promise.all([
    identityClient.getWorkspaceFolderAcl(props.entity.rootId, props.entity.id),
    identityClient.searchWorkspaceAclSubjects(props.entity.rootId),
  ])
  if (result.data) {
    acl.value = result.data
    inherit.value = result.data.inherited
    for (const entry of result.data.entries) {
      const key = `${entry.subjectType}:${entry.subjectId}`
      subjectEntries.value[key] = [...(subjectEntries.value[key] ?? []), entry.action]
    }
    const first = Object.keys(subjectEntries.value)[0]
    if (first) selectSubject(first)
  } else error.value = result.error?.message ?? t('Unable to load permissions')
  if (subjectResult.data) subjects.value = subjectResult.data
  else if (!error.value) error.value = subjectResult.error?.message ?? t('Unable to load ACL subjects')
  loading.value = false
}
async function save() {
  if (!acl.value) return
  saving.value = true; error.value = ''
  if (!inherit.value && selectedSubjectKey.value) {
    subjectEntries.value[selectedSubjectKey.value] = [...selectedActions.value]
  }
  const entries = inherit.value
    ? []
    : Object.entries(subjectEntries.value).flatMap(([key, actions]) => {
      const separator = key.indexOf(':')
      const subjectType = key.slice(0, separator) as 'role' | 'group' | 'user'
      const subjectId = key.slice(separator + 1)
      return actions.map(action => ({ subjectType, subjectId, action }))
    })
  const result = await identityClient.replaceWorkspaceFolderAcl(props.entity.rootId, props.entity.id, { inherit: inherit.value, entries, expectedVersion: acl.value.version })
  saving.value = false
  if (result.data) onDialogOK(result.data)
  else error.value = result.error?.message ?? t('Unable to save permissions')
}
onMounted(load)
</script>
