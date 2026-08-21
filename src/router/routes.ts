import Front from 'src/AppFront.vue'
import MainLayout from 'src/layouts/MainLayout.vue'
import DualViewPage from 'src/pages/DualViewPage.vue'
import NotFoundPage from 'src/pages/NotFoundPage.vue'
import SearchIndex from 'src/pages/SearchIndex.vue'
import type { RouteRecordRaw } from 'vue-router'
import { authRoute } from './auth'
import WorkspaceLayout from 'src/layouts/WorkspaceLayout.vue'
import InvitationLayout from 'src/layouts/InvitationLayout.vue'
import TrashLayout from 'src/layouts/TrashLayout.vue'
import SettingsLayout from 'src/layouts/SettingsLayout.vue'
import WorkspaceOverview from 'src/pages/WorkspaceOverview.vue'
import WorkspaceUsage from 'src/pages/WorkspaceUsage.vue'
import WorkspaceConnectors from 'src/pages/WorkspaceConnectors.vue'
import AccountLayout from 'src/layouts/AccountLayout.vue'
import ChatWelcome from 'src/pages/ChatWelcome.vue'
import PageWelcome from 'src/pages/PageWelcome.vue'
import IndexPage from 'src/pages/IndexPage.vue'
import ProviderWelcome from 'src/pages/ProviderWelcome.vue'
import IndexWelcome from 'src/pages/IndexWelcome.vue'
import ItemWelcome from 'src/pages/ItemWelcome.vue'
import ItemIndex from 'src/pages/ItemIndex.vue'
import ModelPricing from 'src/pages/ModelPricing.vue'
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
          { path: '/', component: IndexPage },
          { path: '/welcome', component: IndexWelcome },
        ],
      },
      {
        path: '/:type(search|chat|page|item|folder|assistant|provider)',
        component: MainLayout,
        children: [
          { path: '/:type(search)', component: SearchIndex },
          { path: '/:type(item)', component: ItemIndex },
          { path: '/:type(chat)/welcome', component: ChatWelcome },
          { path: '/:type(page)/welcome', component: PageWelcome },
          { path: '/:type(provider)/welcome', component: ProviderWelcome },
          { path: '/:type(item)/welcome', component: ItemWelcome },
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
            path: 'usage',
            component: WorkspaceUsage,
            meta: {
              title: t('Usage Logs'),
            },
          },
          {
            path: 'connectors',
            component: WorkspaceConnectors,
            meta: {
              title: t('Connectors'),
            },
          },
        ],
      },
      {
        path: '/models',
        component: ModelPricing,
        meta: {
          title: t('Model Pricing'),
        },
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
          title: t('Settings'),
        },
      },
      {
        path: '/account',
        component: AccountLayout,
        meta: {
          title: t('Account'),
        },
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
