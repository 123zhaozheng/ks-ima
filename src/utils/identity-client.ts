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
type MemberWorkspace = components['schemas']['MemberWorkspace']
type PlatformSettings = components['schemas']['PlatformSettings']
type AuditEventList = components['schemas']['AuditEventList']
type WorkspaceMember = components['schemas']['WorkspaceMember']
type WorkspaceGroup = components['schemas']['WorkspaceGroup']
type Folder = components['schemas']['Folder']
type FolderAcl = components['schemas']['FolderAcl']
type MemberAddRequest = components['schemas']['MemberAddRequest']
type MemberPatchRequest = components['schemas']['MemberPatchRequest']
type FolderCreateRequest = components['schemas']['FolderCreateRequest']
type FolderPatchRequest = components['schemas']['FolderPatchRequest']
type FolderMoveRequest = components['schemas']['FolderMoveRequest']
type FolderReorderRequest = components['schemas']['FolderReorderRequest']
type FolderLifecycleRequest = components['schemas']['FolderLifecycleRequest']
type AclReplaceRequest = components['schemas']['AclReplaceRequest']
type GroupCreateRequest = components['schemas']['GroupCreateRequest']
type InvitationCreateRequest = components['schemas']['InvitationCreateRequest']
type Invitation = components['schemas']['Invitation']
type UserSearchResult = components['schemas']['UserSearchResult']
type AclSubject = components['schemas']['AclSubject']
type PermissionPreviewRequest = components['schemas']['PermissionPreviewRequest']
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
type WorkspaceCapability = components['schemas']['WorkspaceCapability']
type AssignmentList = components['schemas']['AssignmentList']
type AssignmentRequest = components['schemas']['AssignmentRequest']
type ImpactResponse = components['schemas']['ImpactResponse']
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
  listMemberWorkspaces: () => request<WorkspaceList>('/workspaces'),
  getMemberWorkspace: (workspaceId: string) => request<MemberWorkspace>(`/workspaces/${encodeURIComponent(workspaceId)}`),
  listWorkspaceMembers: (workspaceId: string, q = '') => request<WorkspaceMember[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members?q=${encodeURIComponent(q)}`),
  searchWorkspaceUsers: (workspaceId: string, q: string) => request<UserSearchResult[]>(`/workspaces/${encodeURIComponent(workspaceId)}/members/search?q=${encodeURIComponent(q)}`),
  addWorkspaceMember: (workspaceId: string, input: MemberAddRequest) => request<WorkspaceMember>(`/workspaces/${encodeURIComponent(workspaceId)}/members`, { method: 'POST', body: JSON.stringify(input) }),
  updateWorkspaceMember: (workspaceId: string, userId: string, input: MemberPatchRequest) => request<WorkspaceMember>(`/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  removeWorkspaceMember: (workspaceId: string, userId: string, expectedVersion?: number) => request(`/workspaces/${encodeURIComponent(workspaceId)}/members/${encodeURIComponent(userId)}${expectedVersion ? `?expected_version=${expectedVersion}` : ''}`, { method: 'DELETE' }),
  leaveWorkspaceMember: (workspaceId: string) => request(`/workspaces/${encodeURIComponent(workspaceId)}/leave`, { method: 'POST', body: '{}' }),
  listWorkspaceGroups: (workspaceId: string) => request<WorkspaceGroup[]>(`/workspaces/${encodeURIComponent(workspaceId)}/groups`),
  createWorkspaceGroup: (workspaceId: string, input: GroupCreateRequest) => request<WorkspaceGroup>(`/workspaces/${encodeURIComponent(workspaceId)}/groups`, { method: 'POST', body: JSON.stringify(input) }),
  listWorkspaceGroupMembers: (workspaceId: string, groupId: string) => request<UserSearchResult[]>(`/workspaces/${encodeURIComponent(workspaceId)}/groups/${encodeURIComponent(groupId)}/members`),
  deleteWorkspaceGroup: (workspaceId: string, groupId: string) => request(`/workspaces/${encodeURIComponent(workspaceId)}/groups/${encodeURIComponent(groupId)}`, { method: 'DELETE' }),
  addWorkspaceGroupMember: (workspaceId: string, groupId: string, userId: string) => request(`/workspaces/${encodeURIComponent(workspaceId)}/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}`, { method: 'PUT', body: '{}' }),
  removeWorkspaceGroupMember: (workspaceId: string, groupId: string, userId: string) => request(`/workspaces/${encodeURIComponent(workspaceId)}/groups/${encodeURIComponent(groupId)}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
  listWorkspaceFolders: (workspaceId: string, parentId?: string) => request<Folder[]>(`/workspaces/${encodeURIComponent(workspaceId)}/folders${parentId ? `?parent_id=${encodeURIComponent(parentId)}` : ''}`),
  createWorkspaceFolder: (workspaceId: string, input: FolderCreateRequest) => request<Folder>(`/workspaces/${encodeURIComponent(workspaceId)}/folders`, { method: 'POST', body: JSON.stringify(input) }),
  getWorkspaceFolder: (workspaceId: string, folderId: string) => request<Folder>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}`),
  renameWorkspaceFolder: (workspaceId: string, folderId: string, input: FolderPatchRequest) => request<Folder>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}`, { method: 'PATCH', body: JSON.stringify(input) }),
  moveWorkspaceFolder: (workspaceId: string, folderId: string, input: FolderMoveRequest) => request<Folder>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/move`, { method: 'POST', body: JSON.stringify(input) }),
  reorderWorkspaceFolder: (workspaceId: string, folderId: string, input: FolderReorderRequest) => request<Folder>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/reorder`, { method: 'POST', body: JSON.stringify(input) }),
  trashWorkspaceFolder: (workspaceId: string, folderId: string, input: FolderLifecycleRequest) => request(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/trash`, { method: 'POST', body: JSON.stringify(input) }),
  restoreWorkspaceFolder: (workspaceId: string, folderId: string, input: FolderLifecycleRequest) => request(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/restore`, { method: 'POST', body: JSON.stringify(input) }),
  deleteWorkspaceFolder: (workspaceId: string, folderId: string, expectedVersion: number) => request(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}?expected_version=${expectedVersion}`, { method: 'DELETE' }),
  getWorkspaceFolderAcl: (workspaceId: string, folderId: string) => request<FolderAcl>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/acl`),
  searchWorkspaceAclSubjects: (workspaceId: string, q = '') => request<AclSubject[]>(`/workspaces/${encodeURIComponent(workspaceId)}/acl-subjects?q=${encodeURIComponent(q)}`),
  replaceWorkspaceFolderAcl: (workspaceId: string, folderId: string, input: AclReplaceRequest) => request<FolderAcl>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/acl`, { method: 'PUT', body: JSON.stringify(input) }),
  inheritWorkspaceFolderAcl: (workspaceId: string, folderId: string, expectedVersion?: number) => request<FolderAcl>(`/workspaces/${encodeURIComponent(workspaceId)}/folders/${encodeURIComponent(folderId)}/acl${expectedVersion ? `?expected_version=${expectedVersion}` : ''}`, { method: 'DELETE' }),
  issueWorkspaceInvitation: (workspaceId: string, input: InvitationCreateRequest) => request<Invitation>(`/workspaces/${encodeURIComponent(workspaceId)}/invitations`, { method: 'POST', body: JSON.stringify(input) }),
  listWorkspaceInvitations: (workspaceId: string) => request<Invitation[]>(`/workspaces/${encodeURIComponent(workspaceId)}/invitations`),
  revokeWorkspaceInvitation: (workspaceId: string, invitationId: string) => request(`/workspaces/${encodeURIComponent(workspaceId)}/invitations/${encodeURIComponent(invitationId)}`, { method: 'DELETE' }),
  acceptWorkspaceInvitation: (token: string) => request(`/workspace-invitations/${encodeURIComponent(token)}/accept`, { method: 'POST', body: '{}' }),
  previewWorkspacePermissions: (workspaceId: string, input: PermissionPreviewRequest) => request<Folder[]>(`/workspaces/${encodeURIComponent(workspaceId)}/permission-preview`, { method: 'POST', body: JSON.stringify(input) }),
  repairWorkspaceAdmin: (workspaceId: string, userId: string) => request(`/admin/workspaces/${encodeURIComponent(workspaceId)}/workspace-admin-repair`, { method: 'POST', body: JSON.stringify({ userId }) }),
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
  listCapabilityAssignments: (workspaceId: string) => request<AssignmentList>(`/admin/workspaces/${encodeURIComponent(workspaceId)}/profile-assignments`),
  assignCapabilityProfile: (workspaceId: string, workflow: string, input: AssignmentRequest) => request(`/admin/workspaces/${encodeURIComponent(workspaceId)}/profile-assignments/${encodeURIComponent(workflow)}`, { method: 'PUT', body: JSON.stringify(input) }),
  removeCapabilityProfile: (workspaceId: string, workflow: string, expectedVersion?: number) => request(`/admin/workspaces/${encodeURIComponent(workspaceId)}/profile-assignments/${encodeURIComponent(workflow)}${expectedVersion ? `?expected_version=${expectedVersion}` : ''}`, { method: 'DELETE' }),
  modelGovernanceImpact: (modelId: string) => request<ImpactResponse>(`/admin/model-governance/impact?model_id=${encodeURIComponent(modelId)}`),
  workspaceCapabilities: (workspaceId: string) => request<WorkspaceCapability[]>(`/workspaces/${encodeURIComponent(workspaceId)}/capabilities`),
}
