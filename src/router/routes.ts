import Front from 'src/AppFront.vue'
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

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: Front,
    children: [
      {
        path: '/',
        component: MainLayout,
        children: [
          { path: '/', component: AskHome, meta: { title: '提问' } },
          { path: '/ask/:conversationId', component: ConversationView, meta: { title: '提问' } },
          { path: '/kb', component: KnowledgeBase, meta: { title: '知识库' } },
        ],
      },
      {
        path: '/history',
        component: HistoryPage,
        meta: { title: '历史' },
      },
      {
        path: '/connectors',
        component: ConnectorsPage,
        meta: { title: '连接器' },
      },
      {
        path: '/settings',
        component: SettingsLayout,
        meta: {
          title: '设置',
        },
      },
      // Accepting a knowledge base share link replaces the old invitation flow.
      {
        path: '/join/:token',
        component: JoinKnowledgeBase,
        props: true,
        meta: { title: '加入知识库' },
      },
      authRoute,
      { path: '/oauth/consent', component: OAuthConsentPage, meta: { title: '连接智能体' } },
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
]

export default routes
