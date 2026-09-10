import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router'
import routes from './routes'
import { getSession, session } from 'src/utils/identity-client'

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
  if (!to.matched.some(record => record.meta.requiresAdmin)) return true
  if (session.value.isPending) await getSession()
  const roles = session.value.data?.user.platformRoles ?? []
  return roles.some(role => ADMIN_ROLES.includes(role)) ? true : '/'
})

export default router
