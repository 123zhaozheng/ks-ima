import SignInForm from 'src/components/SignInForm.vue'
import SignUpForm from 'src/components/SignUpForm.vue'
import AuthLayout from 'src/layouts/AuthLayout.vue'
import type { RouteRecordRaw } from 'vue-router'
import { t } from 'src/utils/i18n'
import ResetPasswordForm from 'src/components/ResetPasswordForm.vue'
import AcceptInviteForm from 'src/components/AcceptInviteForm.vue'

export const authRoute: RouteRecordRaw = {
  path: '/auth',
  component: AuthLayout,
  children: [
    { path: 'sign-in', component: SignInForm, meta: { title: t('Sign In') } },
    { path: 'sign-up', component: SignUpForm, meta: { title: t('Sign Up') } },
    { path: 'reset-password', component: ResetPasswordForm, meta: { title: t('Reset Password') } },
    { path: 'accept-invite', component: AcceptInviteForm, meta: { title: t('Accept Invitation') } },
  ],
}
