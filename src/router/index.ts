import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router'
import routes from './routes'
import { getSession, session } from 'src/utils/identity-client'
import { watch } from 'vue'

const createHistory = process.env.SERVER
  ? createMemoryHistory
  : (process.env.VUE_ROUTER_MODE === 'history' ? createWebHistory : createWebHashHistory)

const router = createRouter({
  scrollBehavior: () => ({ left: 0, top: 0 }),
  routes,

  // Leave this as is and make changes in quasar.conf.js instead!
  // quasar.conf.js -> build -> vueRouterMode
  // quasar.conf.js -> build -> publicPath
  history: createHistory(process.env.VUE_ROUTER_BASE),
})

// The admin console shares this app; gate its routes by platform role. The
// backend still authorizes every admin API call, this only keeps the UI out of
// non-admin hands.
const ADMIN_ROLES = ['super_admin', 'platform_admin', 'security_auditor']

router.beforeEach(async to => {
  const requiresAuth = to.matched.some(record => record.meta.requiresAuth || record.meta.requiresAdmin)
  const requiresAdmin = to.matched.some(record => record.meta.requiresAdmin)
  if (requiresAuth && session.value.isPending) await getSession()
  if (requiresAuth && !session.value.data?.user) {
    return { path: '/auth/sign-in', query: { redirect: to.fullPath } }
  }
  if (requiresAdmin) {
    const roles = session.value.data?.user.platformRoles ?? []
    if (!roles.some(role => ADMIN_ROLES.includes(role))) return '/'
  }
  return true
})

// Route guards run on navigation. Keep the active protected page in sync when
// a request discovers an expired session while the user is already there.
watch(
  () => [session.value.isPending, session.value.data?.user.id] as const,
  ([isPending, id]) => {
    const route = router.currentRoute.value
    const requiresAuth = route.matched.some(record => record.meta.requiresAuth || record.meta.requiresAdmin)
    if (isPending || id || !requiresAuth) return
    router.replace({ path: '/auth/sign-in', query: { redirect: route.fullPath } })
  },
)

export default router
