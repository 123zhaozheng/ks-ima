import AppShell from 'src/layouts/AppShell.vue'
import MainLayout from 'src/layouts/MainLayout.vue'
import NotFoundPage from 'src/pages/NotFoundPage.vue'
import type { RouteRecordRaw } from 'vue-router'
import { authRoute } from './auth'
import SettingsLayout from 'src/layouts/SettingsLayout.vue'
import ConnectorsPage from 'src/pages/ConnectorsPage.vue'
import KnowledgeBase from 'src/pages/KnowledgeBase.vue'
import AskHome from 'src/pages/AskHome.vue'
import ConversationView from 'src/pages/ConversationView.vue'
import HistoryPage from 'src/pages/HistoryPage.vue'
import JoinKnowledgeBase from 'src/pages/JoinKnowledgeBase.vue'
import OAuthConsentPage from 'src/pages/OAuthConsentPage.vue'

// The admin console is a section of this same app (`/admin/*`), not a separate
// deployment. Its pages are loaded lazily so end users never download them.
const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: AppShell,
    children: [
      {
        path: '/',
        component: MainLayout,
        children: [
          { path: '/', component: AskHome, meta: { title: '提问', requiresAuth: true } },
          { path: '/ask/:conversationId', component: ConversationView, meta: { title: '提问', requiresAuth: true } },
          { path: '/kb', component: KnowledgeBase, meta: { title: '知识库', requiresAuth: true } },
        ],
      },
      {
        path: '/history',
        component: HistoryPage,
        meta: { title: '历史', requiresAuth: true },
      },
      {
        path: '/connectors',
        component: ConnectorsPage,
        meta: { title: '连接器', requiresAuth: true },
      },
      {
        path: '/settings',
        component: SettingsLayout,
        meta: {
          title: '设置',
          requiresAuth: true,
        },
      },
      // Accepting a knowledge base share link replaces the old invitation flow.
      {
        path: '/join/:token',
        component: JoinKnowledgeBase,
        props: true,
        meta: { title: '加入知识库' },
      },
      { path: '/oauth/consent', component: OAuthConsentPage, meta: { title: '连接智能体' } },
      // The admin console shares this shell (compact rail + 56px TopBar); its
      // section chrome and pages stay lazy so users never download them.
      {
        path: '/admin',
        component: () => import('src/admin/layouts/AdminShell.vue'),
        meta: { requiresAuth: true, requiresAdmin: true },
        children: [
          { path: '', component: () => import('src/admin/pages/EmptyPage.vue'), meta: { title: '管理控制台' } },
          { path: 'users', component: () => import('src/admin/pages/UsersPage.vue'), meta: { title: '用户' } },
          { path: 'knowledge-bases', component: () => import('src/admin/pages/KnowledgeBasesPage.vue'), meta: { title: '知识库' } },
          { path: 'models', component: () => import('src/admin/pages/ModelsPage.vue'), meta: { title: '模型配置' } },
          { path: 'audit', component: () => import('src/admin/pages/AuditPage.vue'), meta: { title: '审计' } },
        ],
      },
      // Always leave this as last one,
      // but you can also remove it
      {
        path: '/:catchAll(.*)*',
        component: NotFoundPage,
        meta: {
          title: '未找到页面',
        },
      },
    ],
  },
  // The auth flow renders full-screen without the app shell (no side rail or
  // TopBar): AuthLayout supplies its own split-screen brand layout, so it must
  // sit at the top level alongside AppShell rather than nested inside it.
  authRoute,
]

export default routes
