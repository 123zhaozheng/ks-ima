import SignInForm from 'src/components/SignInForm.vue'
import SignUpForm from 'src/components/SignUpForm.vue'
import AuthLayout from 'src/layouts/AuthLayout.vue'
import type { RouteRecordRaw } from 'vue-router'
import ResetPasswordForm from 'src/components/ResetPasswordForm.vue'
import AcceptInviteForm from 'src/components/AcceptInviteForm.vue'

export const authRoute: RouteRecordRaw = {
  path: '/auth',
  component: AuthLayout,
  children: [
    { path: 'sign-in', component: SignInForm, meta: { title: '登录' } },
    { path: 'sign-up', component: SignUpForm, meta: { title: '注册' } },
    { path: 'reset-password', component: ResetPasswordForm, meta: { title: '重置密码' } },
    { path: 'accept-invite', component: AcceptInviteForm, meta: { title: '接受邀请' } },
  ],
}
