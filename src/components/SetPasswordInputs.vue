<template>
  <div>
    <q-input
      label="密码"
      type="password"
      v-model="password"
      :rules="[
        val => val.length >= 8 || '密码长度必须至少为 8 个字符',
        val => /[a-zA-Z]/.test(val) || '密码必须包含至少一个字母'
      ]"
      :filled
    />
    <q-input
      label="确认密码"
      type="password"
      v-model="confirmPassword"
      :rules="[
        val => val === password || '密码不匹配'
      ]"
      class="mt-2"
      :filled
    />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  filled?: boolean
}>()

const password = defineModel<string>()
const confirmPassword = ref('')
</script>
