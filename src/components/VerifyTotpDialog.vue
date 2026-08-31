<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          双因素验证
        </div>
      </q-card-section>
      <q-card-section py-0>
        {{ recoveryMode ? '输入一个未使用的恢复码。' : '请输入您的身份验证器应用程序中的 TOTP 代码。' }}
      </q-card-section>
      <q-card-section py-2>
        <q-input
          v-model="totp"
          :label="recoveryMode ? '恢复码' : 'TOTP 代码'"
          :type="recoveryMode ? 'text' : 'number'"
        />
      </q-card-section>
      <q-card-actions>
        <q-btn
          flat
          color="primary"
          :label="recoveryMode ? '使用身份验证码' : '使用恢复码'"
          @click="useBackupCode"
        />
        <q-space />
        <q-btn
          flat
          color="primary"
          label="验证"
          :loading
          @click="verify"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { identityClient } from 'src/utils/identity-client'
import { ref } from 'vue'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const { dialogRef, onDialogHide, onDialogOK } = useDialogPluginComponent()
const props = defineProps<{ challenge: string }>()

const totp = ref('')
const recoveryMode = ref(false)

const $q = useQuasar()
const loading = ref(false)
async function verify() {
  loading.value = true

  const result = recoveryMode.value
    ? await identityClient.verifyRecovery({ code: totp.value, challenge: props.challenge })
    : await identityClient.verifyTotp({ code: totp.value, challenge: props.challenge })
  const { error } = result
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      message: `验证失败：${error.message}`,
      color: 'negative',
    })
    return
  }
  onDialogOK()
}

function useBackupCode() { recoveryMode.value = !recoveryMode.value; totp.value = '' }
</script>
