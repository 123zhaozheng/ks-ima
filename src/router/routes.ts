import Front from 'src/AppFront.vue'
import MainLayout from 'src/layouts/MainLayout.vue'
import NotFoundPage from 'src/pages/NotFoundPage.vue'
import type { RouteRecordRaw, RouteLocationGeneric } from 'vue-router'
import { authRoute } from './auth'
import WorkspaceLayout from 'src/layouts/WorkspaceLayout.vue'
import InvitationLayout from 'src/layouts/InvitationLayout.vue'
import TrashLayout from 'src/layouts/TrashLayout.vue'
import SettingsLayout from 'src/layouts/SettingsLayout.vue'
import WorkspaceOverview from 'src/pages/WorkspaceOverview.vue'
import WorkspaceConnectors from 'src/pages/WorkspaceConnectors.vue'
import AccountLayout from 'src/layouts/AccountLayout.vue'
import KnowledgeWorkspace from 'src/pages/KnowledgeWorkspace.vue'
import AccountSecurity from 'src/pages/AccountSecurity.vue'
import WorkspaceModels from 'src/pages/WorkspaceModels.vue'
import WorkspaceTags from 'src/pages/WorkspaceTags.vue'
import AskHome from 'src/pages/AskHome.vue'
import ConversationView from 'src/pages/ConversationView.vue'
import HistoryPage from 'src/pages/HistoryPage.vue'
import OAuthConsentPage from 'src/pages/OAuthConsentPage.vue'
import { t } from 'src/utils/i18n'

function redirectKnowledgeToKb(to: RouteLocationGeneric) {
  return { path: '/kb', query: { ...to.query, doc: String(to.params.documentId) } }
}

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
          { path: '/kb', component: KnowledgeWorkspace, meta: { title: t('Knowledge base') } },
          { path: '/welcome', redirect: '/kb' },
          // Deep links to documents now land in the knowledge workspace.
          { path: '/knowledge/:documentId', redirect: redirectKnowledgeToKb },
        ],
      },
      // Legacy chat deep links are gone with the Zero-bound chat experience;
      // send them to the Ask home instead of a dead end.
      {
        path: '/chat/:rest*',
        redirect: '/',
      },
      {
        path: '/history',
        component: HistoryPage,
        meta: { title: t('History') },
      },
      {
        path: '/connectors',
        component: WorkspaceConnectors,
        meta: { title: t('Connectors') },
      },
      // Preserve deep links from the old workspace-connectors route.
      {
        path: '/workspace/connectors',
        redirect: '/connectors',
      },
      {
        path: '/workspace',
        component: WorkspaceLayout,
        children: [
          {
            path: '',
            component: WorkspaceOverview,
            meta: {
              title: t('Workspace Overview'),
            },
          },
          {
            path: 'models',
            component: WorkspaceModels,
            meta: {
              title: t('Models'),
            },
          },
          {
            path: 'tags',
            component: WorkspaceTags,
            meta: { title: t('Tags') },
          },
        ],
      },
      {
        path: '/trash',
        component: TrashLayout,
        meta: {
          title: t('Trash'),
        },
      },
      {
        path: '/invitations/:token',
        component: InvitationLayout,
        props: true,
      },
      {
        path: '/settings',
        component: SettingsLayout,
        meta: {
          title: t('Personal Settings'),
        },
      },
      {
        path: '/account',
        component: AccountLayout,
        meta: { title: t('Account') },
      },
      {
        path: '/account/security',
        component: AccountSecurity,
        meta: { title: t('Account Security') },
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
