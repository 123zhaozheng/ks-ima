<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 520px)">
      <q-card-section>
        <div class="text-h6">
          平台安全设置
        </div>
      </q-card-section>
      <q-card-section>
        <q-toggle
          v-model="form.allowRegistration"
          label="允许公开注册"
        />
        <q-input
          v-model.number="form.sessionIdleSeconds"
          type="number"
          label="会话空闲时长（秒）"
        />
        <q-input
          v-model.number="form.sessionAbsoluteSeconds"
          type="number"
          label="会话最长时长（秒）"
        />
        <q-input
          v-model.number="form.recentAuthSeconds"
          type="number"
          label="敏感操作验证窗口（秒）"
        />
        <q-banner
          mt-3
          dense
        >
          邮件发送（SMTP）：{{ smtpEnabled ? '已配置' : '未配置' }}
        </q-banner>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          label="取消"
          @click="onDialogCancel"
        /><q-btn
          color="primary"
          label="保存"
          :loading="loading"
          @click="save"
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { onMounted, reactive, ref } from 'vue'
import { identityClient } from 'src/utils/identity-client'

defineEmits([...useDialogPluginComponent.emits])
const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()
const $q = useQuasar()
const loading = ref(false)
const smtpEnabled = ref(false)
const form = reactive({ allowRegistration: false, sessionIdleSeconds: 86400, sessionAbsoluteSeconds: 2592000, recentAuthSeconds: 900 })
onMounted(async () => {
  const result = await identityClient.getSettings()
  if (result.data) { Object.assign(form, result.data); smtpEnabled.value = result.data.smtpEnabled }
})
async function save() {
  loading.value = true
  const result = await identityClient.updateSettings(form)
  if (result.error) $q.notify({ type: 'negative', message: `保存失败：${result.error.message}` })
  else onDialogOK()
  loading.value = false
}
</script>
