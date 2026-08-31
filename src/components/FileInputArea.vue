<template>
  <div
    class="file-input-area"
    border="dashed 2px out"
    flex
    items-center
    justify-center
    cursor-pointer
    @click="fileInput?.click()"
    @dragenter.prevent
    @dragover.prevent
    @drop.stop.prevent="onDrop"
  >
    <div text="center out">
      {{ image ? '点击选择图像' : '点击选择文件' }}<br>
      拖到这里<br>
      或 Ctrl+V 粘贴
    </div>
    <input
      ref="fileInput"
      type="file"
      hidden
      :accept="image ? 'image/*' : accept"
      :multiple
      @change="onInput"
    >
  </div>
</template>

<script setup lang="ts">
import { onUnmounted, useTemplateRef } from 'vue'

const props = defineProps<{
  image?: boolean
  multiple?: boolean
  accept?: string
}>()

const emit = defineEmits<{
  input: [File]
}>()
const fileInput = useTemplateRef('fileInput')

function matches(file: File) {
  return !props.image || file.type.startsWith('image/')
}

function onInput() {
  if (!fileInput.value?.files) return
  for (const file of fileInput.value.files) {
    if (matches(file)) emit('input', file)
  }
  fileInput.value.value = ''
}
function onDrop(event: DragEvent) {
  for (const file of event.dataTransfer?.files ?? []) {
    if (matches(file)) {
      emit('input', file)
      break
    }
  }
}
function onPaste(event: ClipboardEvent) {
  for (const file of event.clipboardData?.files ?? []) {
    if (matches(file)) {
      emit('input', file)
      break
    }
  }
}
addEventListener('paste', onPaste)
onUnmounted(() => removeEventListener('paste', onPaste))
</script>

<style scoped>
.file-input-area {
  min-height: 160px;
  border-radius: var(--tk-radius-lg);
  transition: border-color 0.2s ease, background-color 0.2s ease;
}

.file-input-area:hover {
  border-color: var(--tk-accent);
  background-color: var(--tk-accent-soft);
}
</style>
