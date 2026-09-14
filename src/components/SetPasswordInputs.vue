<template>
  <div>
    <q-input
      label="密码"
      type="password"
      v-model="password"
      autocomplete="new-password"
      :rules="[
        val => val.length >= 8 || '密码长度必须至少为 8 个字符',
        val => /[a-zA-Z]/.test(val) || '密码必须包含至少一个字母'
      ]"
      :outlined
    >
      <template #prepend>
        <q-icon
          name="sym_o_lock"
          size="20px"
        />
      </template>
    </q-input>
    <q-input
      label="确认密码"
      type="password"
      v-model="confirmPassword"
      autocomplete="new-password"
      :rules="[
        val => val === password || '密码不匹配'
      ]"
      class="mt-4"
      :outlined
    >
      <template #prepend>
        <q-icon
          name="sym_o_lock_reset"
          size="20px"
        />
      </template>
    </q-input>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  outlined?: boolean
}>()

const password = defineModel<string>()
const confirmPassword = ref('')
</script>
