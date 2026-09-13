import { ref } from 'vue'
import type { components } from 'src/api/generated/schema'

export type IdentityUser = components['schemas']['IdentityUser']
type SignInRequest = components['schemas']['SignInRequest']
type SignInResponse = components['schemas']['SignInResponse']
type AuthCapabilities = components['schemas']['AuthCapabilities']
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
type PlatformSettings = components['schemas']['PlatformSettings']
type AuditEventList = components['schemas']['AuditEventList']
type KnowledgeBase = components['schemas']['KnowledgeBase']
type KnowledgeBaseList = components['schemas']['KnowledgeBaseList']
type KnowledgeBaseCreateRequest = components['schemas']['KnowledgeBaseCreateRequest']
type KnowledgeBaseCreateResponse = components['schemas']['KnowledgeBaseCreateResponse']
type KnowledgeBaseRenameRequest = components['schemas']['KnowledgeBaseRenameRequest']
type KnowledgeBaseRequest = components['schemas']['KnowledgeBaseRequest']
type KbMember = components['schemas']['KbMember']
type MemberRolePatchRequest = components['schemas']['MemberRolePatchRequest']
type ShareLink = components['schemas']['ShareLink']
type ShareLinkCreateRequest = components['schemas']['ShareLinkCreateRequest']
type Folder = components['schemas']['Folder']
type FolderCreateRequest = components['schemas']['FolderCreateRequest']
type FolderPatchRequest = components['schemas']['FolderPatchRequest']
type FolderMoveRequest = components['schemas']['FolderMoveRequest']
type FolderReorderRequest = components['schemas']['FolderReorderRequest']
type KbCapability = components['schemas']['KbCapability']
type ModelGateway = components['schemas']['ModelGateway']
type ModelGatewayList = components['schemas']['ModelGatewayList']
type GatewayCreateRequest = components['schemas']['GatewayCreateRequest']
type GatewayPatchRequest = components['schemas']['GatewayPatchRequest']
type SecretRotateRequest = components['schemas']['SecretRotateRequest']
type GovernedModel = components['schemas']['GovernedModel']
type GovernedModelList = components['schemas']['GovernedModelList']
type GovernedModelCreateRequest = components['schemas']['GovernedModelCreateRequest']
type GovernedModelPatchRequest = components['schemas']['GovernedModelPatchRequest']
type CapabilityProfile = components['schemas']['CapabilityProfile']
type ProfileList = components['schemas']['ProfileList']
type ProfileVersionList = components['schemas']['ProfileVersionList']
type ProfileCreateRequest = components['schemas']['ProfileCreateRequest']
type ProfilePatchRequest = components['schemas']['ProfilePatchRequest']
type SceneDefaultList = components['schemas']['SceneDefaultList']
type SceneDefaultItem = components['schemas']['SceneDefaultItem']
type ImpactResponse = components['schemas']['ImpactResponse']
type ConsentView = components['schemas']['ConsentView']
type ConsentSubmit = components['schemas']['ConsentSubmit']
type ServicePrincipal = components['schemas']['ServicePrincipalResponse']
type ServicePrincipalCreate = components['schemas']['ServicePrincipalCreate']
type CredentialIssue = components['schemas']['CredentialIssueResponse']
type CredentialRotate = components['schemas']['CredentialRotate']
type ConnectedGrant = components['schemas']['ConnectedGrantResponse']
type ServicePrincipalDetail = components['schemas']['ServicePrincipalDetailResponse']
type Result<T> = { data?: T, error?: { code?: string, message: string } }

/**
 * Knowledge base summary as returned by the member-facing list/get/accept
 * endpoints: the generated KnowledgeBase DTO plus the `owned` marker the
 * backend adds for switcher badges.
 */
export type KnowledgeBaseSummary = KnowledgeBase & { owned: boolean }

async function request<T>(path: string, init: RequestInit = {}, prefix = '/api/v1'): Promise<Result<T>> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  if (!['GET', 'HEAD'].includes(init.method ?? 'GET')) {
    const csrf = document.cookie.split('; ').find(value => value.startsWith('ima_csrf='))?.split('=').slice(1).join('=')
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
  }
  const response = await fetch(`${prefix}${path}`, { ...init, headers, credentials: 'include' })
  // A 401 can mean the cookie session died mid-visit: re-check it so the
  // useRequireLogin watchers redirect to sign-in. A still-valid session
  // (recent-auth 401) survives the re-check; '/auth/session' itself must not loop.
  if (response.status === 401 && path !== '/auth/session') revalidateSession()
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

let sessionRevalidation: Promise<void> | null = null
/** Debounced session re-check fired by any 401 response. */
export function revalidateSession(): Promise<void> {
  sessionRevalidation ??= getSession()
    .then(() => undefined)
    .catch(() => undefined)
    .finally(() => { sessionRevalidation = null })
  return sessionRevalidation
}

export const identityClient = {
  getSession,
  signIn: async (input: SignInRequest): Promise<Result<SignInResponse>> => {
    const result = await request<SignInResponse>('/auth/sign-in', { method: 'POST', body: JSON.stringify(input) })
    if (result.data?.user) await getSession()
    return result
  },
  register: (input: RegisterRequest) => request<IdentityUser>('/auth/register', { method: 'POST', body: JSON.stringify(input) }),
  authCapabilities: () => request<AuthCapabilities>('/auth/capabilities'),
  signOut: async () => { const result = await request('/auth/sign-out', { method: 'POST', body: '{}' }); await getSession(); return result },
  changePassword: (input: PasswordChangeRequest) => request('/account/password/change', { method: 'POST', body: JSON.stringify(input) }),
  requestPasswordReset: (input: PasswordForgotRequest) => request('/auth/password/forgot', { method: 'POST', body: JSON.stringify(input) }),
  resetPassword: (input: PasswordResetRequest) => request('/auth/password/reset', { method: 'POST', body: JSON.stringify(input) }),
  acceptInvite: (input: AcceptTokenRequest) => request<IdentityUser>('/auth/accept-invite', { method: 'POST', body: JSON.stringify(input) }),
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
  // Knowledge bases (member-facing)
  listKnowledgeBases: () => request<KnowledgeBaseSummary[]>('/knowledge-bases'),
  createKnowledgeBase: (input: KnowledgeBaseCreateRequest) => request<KnowledgeBaseCreateResponse>('/knowledge-bases', { method: 'POST', body: JSON.stringify(input) }),
  getKnowledgeBase: (kbId: string) => request<KnowledgeBaseSummary>(`/knowledge-bases/${encodeURIComponent(kbId)}`),
  renameKnowledgeBase: (kbId: string, input: KnowledgeBaseRenameRequest) => request<KnowledgeBaseSummary>(`/knowledge-bases/${encodeURIComponent(kbId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  archiveKnowledgeBase: (kbId: string) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/archive`, { method: 'POST', body: '{}' }),
  restoreKnowledgeBase: (kbId: string) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/restore`, { method: 'POST', body: '{}' }),
  deleteKnowledgeBase: (kbId: string) => request(`/knowledge-bases/${encodeURIComponent(kbId)}`, { method: 'DELETE' }),
  leaveKnowledgeBase: (kbId: string) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/leave`, { method: 'POST', body: '{}' }),
  // Knowledge base members
  listKbMembers: (kbId: string, q = '') => request<KbMember[]>(`/knowledge-bases/${encodeURIComponent(kbId)}/members?q=${encodeURIComponent(q)}`),
  updateKbMemberRole: (kbId: string, userId: string, input: MemberRolePatchRequest) => request<KbMember>(`/knowledge-bases/${encodeURIComponent(kbId)}/members/${encodeURIComponent(userId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  removeKbMember: (kbId: string, userId: string, expectedVersion?: number) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/members/${encodeURIComponent(userId)}${expectedVersion ? `?expected_version=${expectedVersion}` : ''}`, { method: 'DELETE' }),
  // Knowledge base share links
  listKbShareLinks: (kbId: string) => request<ShareLink[]>(`/knowledge-bases/${encodeURIComponent(kbId)}/share-links`),
  createKbShareLink: (kbId: string, input: ShareLinkCreateRequest) => request<ShareLink>(`/knowledge-bases/${encodeURIComponent(kbId)}/share-links`, { method: 'POST', body: JSON.stringify(input) }),
  revokeKbShareLink: (kbId: string, linkId: string) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/share-links/${encodeURIComponent(linkId)}`, { method: 'DELETE' }),
  acceptKbShareLink: (token: string) => request<KnowledgeBaseSummary>(`/kb-share-links/${encodeURIComponent(token)}/accept`, { method: 'POST', body: '{}' }),
  // Knowledge base folder tree
  listKbFolders: (kbId: string) => request<Folder[]>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders`),
  createKbFolder: (kbId: string, input: FolderCreateRequest) => request<Folder>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders`, { method: 'POST', body: JSON.stringify(input) }),
  getKbFolder: (kbId: string, folderId: string) => request<Folder>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}`),
  renameKbFolder: (kbId: string, folderId: string, input: FolderPatchRequest) => request<Folder>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveKbFolder: (kbId: string, folderId: string, input: FolderMoveRequest) => request<Folder>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}/move`, { method: 'POST', body: JSON.stringify(input) }),
  reorderKbFolder: (kbId: string, folderId: string, input: FolderReorderRequest) => request<Folder>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}/reorder`, { method: 'POST', body: JSON.stringify(input) }),
  kbFolderBreadcrumbs: (kbId: string, folderId: string) => request<Folder[]>(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}/breadcrumbs`),
  deleteKbFolder: (kbId: string, folderId: string, expectedVersion: number) => request(`/knowledge-bases/${encodeURIComponent(kbId)}/folders/${encodeURIComponent(folderId)}?expected_version=${expectedVersion}`, { method: 'DELETE' }),
  // Model capabilities assigned to a knowledge base (read-only for members)
  kbModelCapabilities: (kbId: string) => request<KbCapability[]>(`/knowledge-bases/${encodeURIComponent(kbId)}/capabilities`),
  // Platform admin: knowledge bases
  adminListKnowledgeBases: (search = '', cursor?: string) => request<KnowledgeBaseList>(`/admin/knowledge-bases?q=${encodeURIComponent(search)}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''}`),
  adminCreateKnowledgeBase: (input: KnowledgeBaseRequest) => request<KnowledgeBaseCreateResponse>('/admin/knowledge-bases', { method: 'POST', body: JSON.stringify(input) }),
  adminArchiveKnowledgeBase: (id: string) => request(`/admin/knowledge-bases/${id}/archive`, { method: 'POST', body: '{}' }),
  adminRestoreKnowledgeBase: (id: string) => request(`/admin/knowledge-bases/${id}/restore`, { method: 'POST', body: '{}' }),
  adminDeleteKnowledgeBase: (id: string) => request(`/admin/knowledge-bases/${id}`, { method: 'DELETE' }),
  getSettings: () => request<PlatformSettings>('/admin/settings'),
  updateSettings: (input: SettingPatch) => request<PlatformSettings>('/admin/settings', { method: 'PATCH', body: JSON.stringify(input) }),
  listAudit: (limit = 100) => request<AuditEventList>(`/admin/audit-events?limit=${limit}`),
  listModelGateways: () => request<ModelGatewayList>('/admin/model-gateways'),
  createModelGateway: (input: GatewayCreateRequest) => request<ModelGateway>('/admin/model-gateways', { method: 'POST', body: JSON.stringify(input) }),
  updateModelGateway: (id: string, input: GatewayPatchRequest) => request<ModelGateway>(`/admin/model-gateways/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  deleteModelGateway: (id: string) => request(`/admin/model-gateways/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  rotateModelGatewaySecret: (id: string, input: SecretRotateRequest) => request<ModelGateway>(`/admin/model-gateways/${encodeURIComponent(id)}/rotate-secret`, { method: 'POST', body: JSON.stringify(input) }),
  enableModelGateway: (id: string, input: components['schemas']['VersionRequest'] = {}) => request<ModelGateway>(`/admin/model-gateways/${encodeURIComponent(id)}/enable`, { method: 'POST', body: JSON.stringify(input) }),
  disableModelGateway: (id: string, input: components['schemas']['VersionRequest'] = {}) => request<ModelGateway>(`/admin/model-gateways/${encodeURIComponent(id)}/disable`, { method: 'POST', body: JSON.stringify(input) }),
  discoverModelGateway: (id: string) => request<{ names: string[] }>(`/admin/model-gateways/${encodeURIComponent(id)}/discover`, { method: 'POST', body: '{}' }),
  checkModelGatewayHealth: (id: string, capability?: components['schemas']['HealthRequest']['capability']) => request<Record<string, unknown>[]>(`/admin/model-gateways/${encodeURIComponent(id)}/health`, { method: 'POST', body: JSON.stringify({ capability }) }),
  listGovernedModels: () => request<GovernedModelList>('/admin/governed-models'),
  createGovernedModel: (input: GovernedModelCreateRequest) => request<GovernedModel>('/admin/governed-models', { method: 'POST', body: JSON.stringify(input) }),
  updateGovernedModel: (id: string, input: GovernedModelPatchRequest) => request<GovernedModel>(`/admin/governed-models/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  validateGovernedModel: (id: string, input: components['schemas']['VersionRequest'] = {}) => request<GovernedModel>(`/admin/governed-models/${encodeURIComponent(id)}/validate`, { method: 'POST', body: JSON.stringify(input) }),
  enableGovernedModel: (id: string, input: components['schemas']['VersionRequest'] = {}) => request<GovernedModel>(`/admin/governed-models/${encodeURIComponent(id)}/enable`, { method: 'POST', body: JSON.stringify(input) }),
  disableGovernedModel: (id: string, input: components['schemas']['VersionRequest'] = {}) => request<GovernedModel>(`/admin/governed-models/${encodeURIComponent(id)}/disable`, { method: 'POST', body: JSON.stringify(input) }),
  deleteGovernedModel: (id: string) => request(`/admin/governed-models/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  listCapabilityProfiles: () => request<ProfileList>('/admin/capability-profiles'),
  createCapabilityProfile: (input: ProfileCreateRequest) => request<CapabilityProfile>('/admin/capability-profiles', { method: 'POST', body: JSON.stringify(input) }),
  listCapabilityProfileVersions: (id: string) => request<ProfileVersionList>(`/admin/capability-profiles/${encodeURIComponent(id)}/versions`),
  patchCapabilityProfileDraft: (id: string, input: ProfilePatchRequest) => request(`/admin/capability-profiles/${encodeURIComponent(id)}/draft`, { method: 'PATCH', body: JSON.stringify(input) }),
  publishCapabilityProfile: (id: string, input: ProfilePatchRequest) => request(`/admin/capability-profiles/${encodeURIComponent(id)}/publish`, { method: 'POST', body: JSON.stringify(input) }),
  validateCapabilityProfile: (id: string) => request<Record<string, unknown>>(`/admin/capability-profiles/${encodeURIComponent(id)}/validate`, { method: 'POST', body: '{}' }),
  cloneCapabilityProfile: (id: string, input: components['schemas']['ProfileCloneRequest'] = {}) => request<CapabilityProfile>(`/admin/capability-profiles/${encodeURIComponent(id)}/clone`, { method: 'POST', body: JSON.stringify(input) }),
  disableCapabilityProfile: (id: string) => request(`/admin/capability-profiles/${encodeURIComponent(id)}/disable`, { method: 'POST', body: '{}' }),
  restoreCapabilityProfile: (id: string) => request(`/admin/capability-profiles/${encodeURIComponent(id)}/restore`, { method: 'POST', body: '{}' }),
  deleteCapabilityProfile: (id: string) => request(`/admin/capability-profiles/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  listSceneDefaults: () => request<SceneDefaultList>('/admin/scene-defaults'),
  updateSceneDefault: (workflow: string, modelId: string | null) => request<SceneDefaultItem>(`/admin/scene-defaults/${encodeURIComponent(workflow)}`, { method: 'PUT', body: JSON.stringify({ modelId }) }),
  modelGovernanceImpact: (modelId: string) => request<ImpactResponse>(`/admin/model-governance/impact?model_id=${encodeURIComponent(modelId)}`),
  previewOAuthConsent: (query: string) => request<ConsentView>(`/oauth/authorize?${query}`, {}, ''),
  submitOAuthConsent: (input: ConsentSubmit) => request('/oauth/authorize', { method: 'POST', body: JSON.stringify(input) }, ''),
  // Service principals are user-level: they belong to their creator and can
  // reach every knowledge base the creator is a member of.
  listServicePrincipals: () => request<ServicePrincipal[]>('/service-principals'),
  getServicePrincipal: (principalId: string) => request<ServicePrincipalDetail>(`/service-principals/${encodeURIComponent(principalId)}`),
  createServicePrincipal: (input: ServicePrincipalCreate) => request<CredentialIssue>('/service-principals', { method: 'POST', body: JSON.stringify(input) }),
  rotateServiceCredential: (principalId: string, credentialId: string, input: CredentialRotate) => request<CredentialIssue>(`/service-principals/${encodeURIComponent(principalId)}/credentials/${encodeURIComponent(credentialId)}/rotate`, { method: 'POST', body: JSON.stringify(input) }),
  revokeServiceCredential: (principalId: string, credentialId: string) => request(`/service-principals/${encodeURIComponent(principalId)}/credentials/${encodeURIComponent(credentialId)}`, { method: 'DELETE' }),
  revokeServicePrincipal: (principalId: string) => request(`/service-principals/${encodeURIComponent(principalId)}`, { method: 'DELETE' }),
  listConnectedOAuthGrants: () => request<ConnectedGrant[]>('/oauth/grants'),
  revokeConnectedOAuthGrant: (grantId: string) => request(`/oauth/grants/${encodeURIComponent(grantId)}`, { method: 'DELETE' }),
}
