<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          封禁用户
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item label="封禁原因">
            <q-input
              v-model="reason"
              dense
              field-sizing-content
              min-w="120px"
            />
          </common-item>
          <common-item label="封禁时长">
            <q-input
              v-model.number="periodDays"
              type="number"
              placeholder="永久"
              suffix="天"
              dense
              class="w-120px"
            />
          </common-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          label="取消"
          @click="onDialogCancel"
        />
        <q-btn
          flat
          color="primary"
          label="封禁"
          @click="banUser"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { ref } from 'vue'
import CommonItem from '../../components/CommonItem.vue'
import { identityClient } from 'src/utils/identity-client'

type UserWithRole = { id: string, displayName: string, email: string, isActive: boolean }

defineEmits([
  ...useDialogPluginComponent.emits,
])

const props = defineProps<{
  user: UserWithRole
}>()

const reason = ref('')
const periodDays = ref<number | null>(null)

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const $q = useQuasar()
async function banUser() {
  loading.value = true
  const result = await identityClient.disableUser(props.user.id)
  if (!result.error) {
    onDialogOK()
  } else {
    $q.notify({
      message: `未能封禁用户：${result.error.message}`,
      color: 'negative',
    })
  }
  loading.value = false
}
</script>
