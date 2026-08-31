<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          忘记密码
        </div>
      </q-card-section>
      <q-card-section py-0>
        请输入您的电子邮件。 我们将向您发送一个重置密码的链接。
      </q-card-section>
      <q-form @submit="send">
        <q-card-section py-2>
          <q-input
            v-model="email"
            label="电子邮件"
            type="email"
            required
          />
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
            label="发送"
            :loading
            type="submit"
          />
        </q-card-actions>
      </q-form>
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

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const email = ref('')

const $q = useQuasar()
const loading = ref(false)
async function send() {
  loading.value = true

  const { error } = await identityClient.requestPasswordReset({
    email: email.value,
  })
  loading.value = false
  if (error) {
    console.error(error)
    $q.notify({
      message: `请求重置密码失败：${error.message}`,
      color: 'negative',
    })
    return
  }
  $q.notify('密码重置邮件已发送')
  onDialogOK()
}
</script>
