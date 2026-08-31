<template>
  <q-dialog
    ref="dialogRef"
    persistent
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          需要再次验证身份
        </div>
      </q-card-section>
      <q-card-section class="q-pt-none text-grey-7">
        该操作属于敏感操作，之前的登录验证已过期。请输入密码继续。
      </q-card-section>
      <q-card-section class="q-pt-none">
        <q-input
          v-model="password"
          type="password"
          label="密码"
          dense
          outlined
          autofocus
          :error="!!errorMessage"
          :error-message="errorMessage"
          @keyup.enter="submit"
        />
      </q-card-section>
      <q-card-actions
        align="right"
        class="q-px-md q-pb-md"
      >
        <q-btn
          flat
          no-caps
          label="取消"
          :disable="busy"
          @click="onDialogCancel"
        />
        <q-btn
          color="primary"
          unelevated
          no-caps
          label="验证"
          :loading="busy"
          @click="submit"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDialogPluginComponent } from 'quasar'
import { identityClient, session } from 'src/utils/identity-client'
import { apiErrorMessage } from 'src/utils/api-error'

defineEmits([
  ...useDialogPluginComponent.emits,
])

// ok 时若携带字符串，表示还需要完成 TOTP 二次验证。
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const password = ref('')
const busy = ref(false)
const errorMessage = ref('')

async function submit() {
  const email = session.value.data?.user.email
  if (!email) { onDialogCancel(); return }
  if (!password.value) {
    errorMessage.value = '请输入密码'
    return
  }
  busy.value = true
  errorMessage.value = ''
  const result = await identityClient.signIn({ email, password: password.value })
  busy.value = false
  if (result.data?.status === 'totp_required' && result.data.challenge) {
    onDialogOK(result.data.challenge)
    return
  }
  if (result.error) {
    errorMessage.value = apiErrorMessage(result.error, '验证失败，请检查密码')
    return
  }
  onDialogOK()
}
</script>
