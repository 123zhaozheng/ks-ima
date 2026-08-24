<template>
  <q-dialog
    ref="dialogRef"
    @hide="onDialogHide"
    no-refocus
  >
    <q-card style="width: min(90vw, 400px)">
      <q-card-section>
        <div class="text-h6">
          {{ t('Create User') }}
        </div>
      </q-card-section>
      <q-card-section p-0>
        <q-list>
          <common-item :label="t('Name')">
            <q-input
              v-model="model.name"
              dense
            />
          </common-item>
          <common-item :label="t('Email')">
            <q-input
              v-model="model.email"
              type="email"
              dense
            />
          </common-item>
          <common-item :label="t('Password')">
            <q-input
              v-model="model.password"
              type="password"
              :rules="[val => val.length >= 12 || t('Password must be at least 12 characters long')]"
              dense
            />
          </common-item>
        </q-list>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn
          flat
          color="primary"
          :label="t('Cancel')"
          @click="onDialogCancel"
        />
        <q-btn
          flat
          color="primary"
          :label="t('Create')"
          @click="createUser"
          :disable="!model.name || !model.email || model.password.length < 12"
          :loading
        />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { useDialogPluginComponent, useQuasar } from 'quasar'
import { t } from 'src/utils/i18n'
import { reactive, ref } from 'vue'
import { identityClient } from 'src/utils/identity-client'
import CommonItem from '../../components/CommonItem.vue'

defineEmits([
  ...useDialogPluginComponent.emits,
])

const model = reactive({
  name: '',
  email: '',
  password: '',
})

const { dialogRef, onDialogHide, onDialogOK, onDialogCancel } = useDialogPluginComponent()

const loading = ref(false)
const $q = useQuasar()
async function createUser() {
  loading.value = true
  const result = await identityClient.createUser({
    email: model.email,
    displayName: model.name,
    temporaryPassword: model.password,
    sendInvite: false,
  })
  if (!result.error) {
    onDialogOK()
  } else {
    $q.notify({
      message: t('Failed to create user: {0}', result.error.message),
      color: 'negative',
    })
  }
  loading.value = false
}
</script>
