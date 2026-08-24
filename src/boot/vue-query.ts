import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import type { boot } from 'quasar/wrappers'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})

export default (() => {
  return (bootContext => {
    bootContext.app.use(VueQueryPlugin, { queryClient })
  }) as ReturnType<typeof boot>
})()

export { queryClient }
