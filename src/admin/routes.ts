import Admin from './AppAdmin.vue'
import type { RouteRecordRaw } from 'vue-router'
import UsersPage from './pages/UsersPage.vue'
import EmptyPage from './pages/EmptyPage.vue'
import NotFoundPage from 'src/pages/NotFoundPage.vue'
import MainLayout from 'src/admin/layouts/MainLayout.vue'
import { authRoute } from 'src/router/auth'
import ModelsPage from './pages/ModelsPage.vue'
import KnowledgeBasesPage from './pages/KnowledgeBasesPage.vue'
import AuditPage from './pages/AuditPage.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    component: Admin,
    children: [
      authRoute,
      {
        path: '/',
        component: MainLayout,
        children: [
          {
            path: '/',
            component: EmptyPage,
          },
          {
            path: '/users',
            component: UsersPage,
            meta: {
              title: '用户',
            },
          },
          {
            path: '/knowledge-bases',
            component: KnowledgeBasesPage,
            meta: {
              title: '知识库',
            },
          },
          {
            path: '/models',
            component: ModelsPage,
            meta: {
              title: '模型配置',
            },
          },
          {
            path: '/audit',
            component: AuditPage,
            meta: { title: '审计' },
          },
          {
            path: '/:catchAll(.*)*',
            component: NotFoundPage,
          },
        ],
      },
    ],
  },
]

export default routes
