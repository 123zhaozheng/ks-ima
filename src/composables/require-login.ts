import { session } from 'src/utils/identity-client'
import { watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

export function useRequireLogin() {
  const route = useRoute()
  const router = useRouter()
  watch(() => [session.value.isPending, session.value.data?.user.id] as const, ([isPending, id]) => {
    if (isPending) return
    if (!id) router.replace({ path: '/auth/sign-in', query: { redirect: route.fullPath } })
  }, { immediate: true })
}
