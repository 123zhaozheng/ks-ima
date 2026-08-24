<template>
  <div class="file-preview">
    <q-inner-loading :showing="loading" />
    <div
      v-if="error"
      text-warn
      p-4
    >
      {{ error }}
    </div>
    <vue-office-docx
      v-else-if="kind === 'docx' && src"
      :src="src"
      class="file-preview__doc"
    />
    <vue-office-excel
      v-else-if="kind === 'xlsx' && src"
      :src="src"
      class="file-preview__doc"
    />
    <vue-office-pdf
      v-else-if="kind === 'pdf' && src"
      :src="src"
      class="file-preview__doc"
    />
  </div>
</template>

<script setup lang="ts">
import { getBlob } from 'src/utils/blob-cache'
import { t } from 'src/utils/i18n'
import { ref, watch } from 'vue'
import VueOfficeDocx from '@vue-office/docx/lib/v3/index.js'
import VueOfficeExcel from '@vue-office/excel/lib/v3/index.js'
import VueOfficePdf from '@vue-office/pdf/lib/v3/index.js'
import '@vue-office/docx/lib/v3/index.css'
import '@vue-office/excel/lib/v3/index.css'

const props = defineProps<{
  itemId: string
  kind: 'docx' | 'xlsx' | 'pdf'
}>()

const src = ref<ArrayBuffer | null>(null)
const loading = ref(false)
const error = ref('')

watch(() => props.itemId, async id => {
  src.value = null
  error.value = ''
  if (!id) return
  loading.value = true
  try {
    const blob = await getBlob(id)
    src.value = await blob.arrayBuffer()
  } catch (err) {
    error.value = t('Failed to load preview: {0}', err instanceof Error ? err.message : String(err))
  } finally {
    loading.value = false
  }
}, { immediate: true })
</script>

<style scoped>
.file-preview {
  position: relative;
  height: 100%;
  min-height: 70vh;
}
.file-preview__doc {
  height: 100%;
  min-height: 70vh;
}
</style>
