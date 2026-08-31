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
import { t } from 'src/utils/i18n'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: Front,
    children: [
      {
        path: '/',
        component: MainLayout,
        children: [
          { path: '/', component: AskHome, meta: { title: t('Ask') } },
          { path: '/ask/:conversationId', component: ConversationView, meta: { title: t('Ask') } },
          { path: '/kb', component: KnowledgeBase, meta: { title: t('Knowledge base') } },
        ],
      },
      {
        path: '/history',
        component: HistoryPage,
        meta: { title: t('History') },
      },
      {
        path: '/connectors',
        component: ConnectorsPage,
        meta: { title: t('Connectors') },
      },
      {
        path: '/settings',
        component: SettingsLayout,
        meta: {
          title: t('Settings'),
        },
      },
      // Accepting a knowledge base share link replaces the old invitation flow.
      {
        path: '/join/:token',
        component: JoinKnowledgeBase,
        props: true,
        meta: { title: t('Join knowledge base') },
      },
      authRoute,
      { path: '/oauth/consent', component: OAuthConsentPage, meta: { title: t('Connect agent') } },
      // Always leave this as last one,
      // but you can also remove it
      {
        path: '/:catchAll(.*)*',
        component: NotFoundPage,
        meta: {
          title: t('Not Found'),
        },
      },
    ],
  },
]

export default routes
