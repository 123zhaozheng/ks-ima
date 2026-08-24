<template>
  <q-item
    clickable
    @click="openTaskPanel"
    :title="t('Tasks')"
  >
    <q-item-section avatar>
      <q-icon name="sym_o_checklist" />
    </q-item-section>
    <q-item-section>
      {{ t('Tasks') }}
    </q-item-section>
    <q-item-section
      v-if="runningTaskCount"
      side
    >
      <q-badge
        :label="runningTaskCount"
        rounded
      />
    </q-item-section>
  </q-item>
</template>
<script lang="ts" setup>
import { t } from 'src/utils/i18n'
import { useQuasar } from 'quasar'
import TaskPanel from './TaskPanel.vue'
import { computed } from 'vue'
import { tasks } from 'src/utils/tasks'

const runningTaskCount = computed(() => tasks.filter(t => t.status === 'running').length)

const $q = useQuasar()
function openTaskPanel() {
  $q.dialog({
    component: TaskPanel,
  })
}
</script>
