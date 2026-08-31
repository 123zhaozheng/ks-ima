import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { useKbStore } from 'src/stores/knowledge-base'
import { session } from 'src/utils/identity-client'

export const useReadonlyStateStore = defineStore('readonlyState', () => {
  const kbStore = useKbStore()

  const message = computed(() => {
    if (!session.value.isPending && session.value.error) {
      return '当前连接发生错误。'
    }
    if (kbStore.member?.role === 'viewer') {
      return '你的角色为只读，只能浏览此知识库的内容，无法修改。'
    }
    return null
  })
  const readonly = computed(() => message.value !== null)

  return {
    message,
    readonly,
  }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(useReadonlyStateStore, import.meta.hot))
}
