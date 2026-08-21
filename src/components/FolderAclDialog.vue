<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 480px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Folder permissions') }}
        </div>
        <div
          text-on-sur-var
          text-sm
          mt-1
        >
          {{ t('Break inheritance to restrict this folder. Users without access will not see it in search, chat, or MCP.') }}
        </div>
      </q-card-section>
      <q-card-section>
        <q-toggle
          v-model="inherit"
          :label="t('Inherit from parent')"
        />
        <div
          v-if="!inherit"
          mt-3
          flex="~ col"
          gap-2
        >
          <q-option-group
            v-model="guestActions"
            type="checkbox"
            :options="actionOptions"
            :label="t('Guest')"
          />
          <div text-sm>
            {{ t('Member / admin keep their default abilities unless you only grant specific users.') }}
          </div>
          <q-input
            v-model="extraUserId"
            :label="t('Grant user ID')"
            dense
            filled
          />
        </div>
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
          :label="t('Save')"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent } from 'quasar'
import { ref } from 'vue'
import { t } from 'src/utils/i18n'
import type { FullEntity } from 'app/src-shared/queries'
import { mutate } from 'src/utils/zero-session'
import { mutators } from 'app/src-shared/mutators'
import { parseFolderAcl, type AclAction, type FolderAcl } from 'app/src-shared/utils/acl'

const props = defineProps<{
  entity: FullEntity
}>()

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const existing = parseFolderAcl(props.entity.conf)
const inherit = ref(existing?.inherit !== false)
const guestActions = ref<AclAction[]>(existing?.aces.find(a => a.principalType === 'role' && a.principalId === 'guest')?.actions ?? ['view', 'ask'])
const extraUserId = ref('')
const actionOptions = [
  { label: t('View'), value: 'view' },
  { label: t('Ask'), value: 'ask' },
  { label: t('Edit'), value: 'edit' },
]

async function save() {
  const acl: FolderAcl = inherit.value
    ? { inherit: true, aces: [] }
    : {
        inherit: false,
        aces: [
          { principalType: 'role', principalId: 'admin', actions: ['view', 'ask', 'edit', 'delete', 'manage'] },
          { principalType: 'role', principalId: 'member', actions: ['view', 'ask', 'edit', 'delete'] },
          { principalType: 'role', principalId: 'guest', actions: guestActions.value },
          ...extraUserId.value
            ? [{ principalType: 'user' as const, principalId: extraUserId.value.trim(), actions: ['view', 'ask', 'edit'] as AclAction[] }]
            : [],
        ],
      }
  await mutate(mutators.updateEntityConf({
    id: props.entity.id,
    updates: { acl },
  })).client
  onDialogOK()
}
</script>
