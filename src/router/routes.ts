import Front from 'src/AppFront.vue'
import MainLayout from 'src/layouts/MainLayout.vue'
import DualViewPage from 'src/pages/DualViewPage.vue'
import NotFoundPage from 'src/pages/NotFoundPage.vue'
import type { RouteRecordRaw } from 'vue-router'
import { authRoute } from './auth'
import WorkspaceLayout from 'src/layouts/WorkspaceLayout.vue'
import InvitationLayout from 'src/layouts/InvitationLayout.vue'
import TrashLayout from 'src/layouts/TrashLayout.vue'
import SettingsLayout from 'src/layouts/SettingsLayout.vue'
import WorkspaceOverview from 'src/pages/WorkspaceOverview.vue'
import WorkspaceConnectors from 'src/pages/WorkspaceConnectors.vue'
import AccountLayout from 'src/layouts/AccountLayout.vue'
import RedirectToFolder from 'src/pages/RedirectToFolder.vue'
import AccountSecurity from 'src/pages/AccountSecurity.vue'
import WorkspaceModels from 'src/pages/WorkspaceModels.vue'
import WorkspaceTags from 'src/pages/WorkspaceTags.vue'
import KnowledgeDocumentPage from 'src/pages/KnowledgeDocumentPage.vue'
import GroundedAskPage from 'src/pages/GroundedAskPage.vue'
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
          { path: '/', component: RedirectToFolder },
          { path: '/welcome', component: RedirectToFolder },
          { path: '/knowledge/:documentId', component: KnowledgeDocumentPage },
        ],
      },
      {
        path: '/:type(chat|item|folder)',
        component: MainLayout,
        children: [
          { path: '/:type(item)', component: RedirectToFolder },
          { path: '/:type(chat)/welcome', component: RedirectToFolder },
          { path: '/:type(item)/welcome', component: RedirectToFolder },
          { path: ':id', component: DualViewPage },
        ],
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
            path: 'connectors',
            component: WorkspaceConnectors,
            meta: {
              title: t('Connectors'),
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
          {
            path: 'ask',
            component: GroundedAskPage,
            meta: { title: t('Ask') },
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
