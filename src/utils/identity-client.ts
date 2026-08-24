import { ref } from 'vue'
import type { components } from 'src/api/generated/schema'

export type IdentityUser = components['schemas']['IdentityUser']
type SignInRequest = components['schemas']['SignInRequest']
type SignInResponse = components['schemas']['SignInResponse']
type RegisterRequest = components['schemas']['RegisterRequest']
type PasswordChangeRequest = components['schemas']['PasswordChangeRequest']
type PasswordResetRequest = components['schemas']['PasswordResetRequest']
type AcceptTokenRequest = components['schemas']['AcceptTokenRequest']
type PasswordForgotRequest = components['schemas']['PasswordForgotRequest']
type TotpVerifyRequest = components['schemas']['TotpVerifyRequest']
type RecoveryVerifyRequest = components['schemas']['RecoveryVerifyRequest']
type SessionInfo = components['schemas']['SessionInfo']
type AdminUserList = components['schemas']['AdminUserList']
type AdminUserInput = components['schemas']['CreateUserRequest']
type AdminProfilePatch = components['schemas']['UserPatch']
type ProfilePatch = components['schemas']['ProfilePatch']
type SettingPatch = components['schemas']['SettingPatch']
type WorkspaceRequest = components['schemas']['WorkspaceRequest']
type WorkspaceList = components['schemas']['WorkspaceList']
type PlatformSettings = components['schemas']['PlatformSettings']
type AuditEventList = components['schemas']['AuditEventList']
type Result<T> = { data?: T, error?: { code?: string, message: string } }

async function request<T>(path: string, init: RequestInit = {}): Promise<Result<T>> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD'].includes(init.method ?? 'GET')) {
    const csrf = document.cookie.split('; ').find(value => value.startsWith('ima_csrf='))?.split('=').slice(1).join('=')
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: 'include' })
  const body = await response.json().catch(() => ({})) as T & { detail?: string, code?: string }
  return response.ok ? { data: body } : { error: { code: body.code, message: body.detail ?? 'Request failed' } }
}

export const session = ref<{ isPending: boolean, error: unknown, data: { user: IdentityUser } | null }>({ isPending: true, error: null, data: null })
export async function getSession(): Promise<Result<IdentityUser>> {
  session.value = { ...session.value, isPending: true }
  const result = await request<IdentityUser>('/auth/session')
  session.value = result.data ? { isPending: false, error: null, data: { user: result.data } } : { isPending: false, error: result.error ?? null, data: null }
  return result
}
getSession().catch(() => undefined)

export const identityClient = {
  getSession,
  signIn: async (input: SignInRequest): Promise<Result<SignInResponse>> => {
    const result = await request<SignInResponse>('/auth/sign-in', { method: 'POST', body: JSON.stringify(input) })
    if (result.data?.user) await getSession()
    return result
  },
  register: (input: RegisterRequest) => request<IdentityUser>('/auth/register', { method: 'POST', body: JSON.stringify(input) }),
  signOut: async () => { const result = await request('/auth/sign-out', { method: 'POST', body: '{}' }); await getSession(); return result },
  changePassword: (input: PasswordChangeRequest) => request('/account/password/change', { method: 'POST', body: JSON.stringify(input) }),
  requestPasswordReset: (input: PasswordForgotRequest) => request('/auth/password/forgot', { method: 'POST', body: JSON.stringify(input) }),
  resetPassword: (input: PasswordResetRequest) => request('/auth/password/reset', { method: 'POST', body: JSON.stringify(input) }),
  acceptInvite: (input: AcceptTokenRequest) => request<IdentityUser>('/auth/invitations/accept', { method: 'POST', body: JSON.stringify(input) }),
  verifyTotp: async (input: TotpVerifyRequest) => {
    const result = await request<IdentityUser>('/auth/totp/verify', { method: 'POST', body: JSON.stringify(input) })
    if (result.data) await getSession()
    return result
  },
  verifyRecovery: async (input: RecoveryVerifyRequest) => {
    const result = await request<IdentityUser>('/auth/recovery/verify', { method: 'POST', body: JSON.stringify(input) })
    if (result.data) await getSession()
    return result
  },
  profile: () => request<IdentityUser>('/account/profile'),
  updateProfile: (input: ProfilePatch) => request<IdentityUser>('/account/profile', { method: 'PATCH', body: JSON.stringify(input) }),
  listSessions: () => request<SessionInfo[]>('/account/sessions'),
  revokeSession: (id: string) => request(`/account/sessions/${id}`, { method: 'DELETE' }),
  revokeAllSessions: () => request('/account/sessions', { method: 'DELETE' }),
  startTotp: () => request<{ otpauthUri: string }>('/account/totp/start', { method: 'POST', body: '{}' }),
  confirmTotp: (code: string) => request<{ recoveryCodes: string[] }>('/account/totp/confirm', { method: 'POST', body: JSON.stringify({ code }) }),
  disableTotp: () => request('/account/totp', { method: 'DELETE' }),
  listUsers: (search = '', cursor?: string) => request<AdminUserList>(`/admin/users?q=${encodeURIComponent(search)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`),
  createUser: (input: AdminUserInput) => request('/admin/users', { method: 'POST', body: JSON.stringify(input) }),
  updateUser: (userId: string, input: AdminProfilePatch) => request(`/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(input) }),
  setPassword: (userId: string, password: string) => request(`/admin/users/${userId}/reset-password`, { method: 'POST', body: JSON.stringify({ password }) }),
  revokeSessions: (userId: string) => request(`/admin/users/${userId}/revoke-sessions`, { method: 'POST', body: '{}' }),
  deleteUser: (userId: string) => request(`/admin/users/${userId}`, { method: 'DELETE' }),
  disableUser: (userId: string) => request(`/admin/users/${userId}/disable`, { method: 'POST', body: '{}' }),
  restoreUser: (userId: string) => request(`/admin/users/${userId}/restore`, { method: 'POST', body: '{}' }),
  resetTotp: (userId: string) => request(`/admin/users/${userId}/reset-totp`, { method: 'POST', body: '{}' }),
  grantRole: (userId: string, role: string) => request(`/admin/users/${userId}/roles/${role}`, { method: 'PUT', body: '{}' }),
  revokeRole: (userId: string, role: string) => request(`/admin/users/${userId}/roles/${role}`, { method: 'DELETE' }),
  listWorkspaces: (search = '', cursor?: string) => request<WorkspaceList>(`/admin/workspaces?q=${encodeURIComponent(search)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`),
  createWorkspace: (input: WorkspaceRequest) => request('/admin/workspaces', { method: 'POST', body: JSON.stringify(input) }),
  archiveWorkspace: (id: string) => request(`/admin/workspaces/${id}/archive`, { method: 'POST', body: '{}' }),
  restoreWorkspace: (id: string) => request(`/admin/workspaces/${id}/restore`, { method: 'POST', body: '{}' }),
  deleteWorkspace: (id: string) => request(`/admin/workspaces/${id}`, { method: 'DELETE' }),
  getSettings: () => request<PlatformSettings>('/admin/settings'),
  updateSettings: (input: SettingPatch) => request<PlatformSettings>('/admin/settings', { method: 'PATCH', body: JSON.stringify(input) }),
  listAudit: (limit = 100) => request<AuditEventList>(`/admin/audit-events?limit=${limit}`),
}
