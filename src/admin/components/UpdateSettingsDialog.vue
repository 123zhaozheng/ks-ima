<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
  >
    <q-card style="width: min(90vw, 520px)">
      <q-card-section>
        <div class="text-h6">
          Platform security settings
        </div>
      </q-card-section>
      <q-card-section>
        <q-toggle
          v-model="form.allowRegistration"
          label="Allow open registration"
        />
        <q-input
          v-model.number="form.sessionIdleSeconds"
          type="number"
          label="Session idle seconds"
        />
        <q-input
          v-model.number="form.sessionAbsoluteSeconds"
          type="number"
          label="Session absolute seconds"
        />
        <q-input
          v-model.number="form.recentAuthSeconds"
          type="number"
          label="Recent authentication window"
        />
        <q-banner
          mt-3
          dense
        >
          SMTP delivery is {{ smtpEnabled ? 'configured' : 'unavailable' }}.
        </q-banner>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          label="Cancel"
          @click="onDialogCancel"
        /><q-btn
          color="primary"
          label="Save"
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
  if (result.error) $q.notify({ type: 'negative', message: result.error.message })
  else onDialogOK()
  loading.value = false
}
</script>
