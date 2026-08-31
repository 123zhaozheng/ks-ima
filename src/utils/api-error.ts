import { IMAApiError } from 'src/api/ima-client'

/**
 * Maps backend problem-details error codes to actionable Chinese messages.
 * The keys are the stable `code` values raised by the backend (see
 * backend/src/ima/application/*.py).
 */
const CODE_MESSAGES: Record<string, string> = {
  FOLDER_NOT_FOUND: '找不到该文件夹。它可能已被删除，或你没有访问权限。',
  DOCUMENT_NOT_FOUND: '找不到该项目。它可能已被删除，或你没有访问权限。',
  KB_NOT_FOUND: '找不到该知识库。它可能已被删除，或你没有访问权限。',
  USER_NOT_FOUND: '找不到该用户。',
  MEMBER_NOT_FOUND: '找不到该成员。',
  CONVERSATION_NOT_FOUND: '找不到该对话。它可能已被删除。',
  VERSION_NOT_FOUND: '找不到该版本。',
  ASSIGNMENT_NOT_FOUND: '未找到该知识库的模型分配。',
  NO_ASSIGNMENT: '该知识库尚未分配 AI 模型。请联系平台管理员分配。',
  MODEL_UNAVAILABLE: '分配的 AI 模型不可用。请联系管理员检查模型网关。',
  STORAGE_UNAVAILABLE: '文件存储暂时不可用，请稍后重试。',
  MEMBERSHIP_FORBIDDEN: '你没有该知识库所需的成员身份。',
  KB_EDITOR_REQUIRED: '此操作需要知识库的编辑权限。',
  KB_ARCHIVED: '该知识库已归档，无法再更改。',
  KB_ACTIVE: '该知识库已处于启用状态。',
  KB_NOT_ARCHIVED: '只有已归档的知识库才能删除。',
  KB_CONTENT_DEPENDENCY: '该知识库仍有内容，需要先移除。',
  NAME_CONFLICT: '该名称已被使用，请换一个。',
  INVALID_KB_NAME: '该知识库名称无效。',
  SHARE_LINK_INVALID: '该分享链接无效或已被撤销。',
  SHARE_LINK_EXPIRED: '该分享链接已过期。',
  SHARE_LINK_NOT_FOUND: '找不到该分享链接。',
  SHARE_LINK_FORBIDDEN: '只有知识库所有者可以管理分享链接。',
  ACCESS_REVOKED: '你对该知识库的访问权限已被撤销。',
  VERSION_CONFLICT: '该内容已被他人修改。请刷新后重试。',
  CONTENT_TOO_LARGE: '内容过大，无法保存。',
  BODY_TOO_LARGE: '文件过大，无法上传。',
  INVALID_TITLE: '该标题无效。',
  INVALID_CURSOR: '分页游标无效。',
  NOT_A_NOTE: '只有笔记支持 Markdown 内容。',
  CROSS_KB: '目标位置不在该知识库内。',
  VALIDATION_ERROR: '请求无效，请检查输入内容。',
  IDENTITY_ERROR: '登录已失效，请重新登录。',
  INTERNAL_ERROR: '服务端出了点问题，请重试。',
  HTTP_401: '登录已失效，或该操作需要重新登录验证，请登录后重试。',
  HTTP_403: '你没有权限执行此操作。',
  HTTP_404: '该操作当前不可用。',
  HTTP_409: '请求与当前状态冲突，请刷新后重试。',
  HTTP_429: '请求过于频繁，请稍后再试。',
}

/**
 * Extracts a stable problem-details code from any thrown or returned value:
 * IMAApiError instances, plain Error subclasses carrying a `code`, Error
 * messages that double as codes, and the plain `{ code, message }` result
 * objects produced by identityClient.
 */
function extractCode(error: unknown): string | undefined {
  if (error instanceof IMAApiError) return error.problem?.code
  if (error instanceof Error) {
    const code = (error as Error & { code?: string }).code
    if (code) return code
    if (error.message && CODE_MESSAGES[error.message]) return error.message
    return undefined
  }
  if (error && typeof error === 'object') {
    const code = (error as { code?: unknown }).code
    if (typeof code === 'string' && code) return code
  }
  return undefined
}

/**
 * Returns a user-facing Chinese message for an arbitrary thrown value.
 * Prefers a mapped problem-details code, then the caller-provided fallback.
 * Callers must pass a Chinese fallback string.
 */
export function apiErrorMessage(error: unknown, fallback = '出错了，请重试。'): string {
  const code = extractCode(error)
  if (code && CODE_MESSAGES[code]) return CODE_MESSAGES[code]
  return fallback
}

/**
 * Returns the raw problem-details code for a thrown value, when available.
 * Useful for branching UI behavior (e.g. showing a "manage models" CTA only
 * when the failure is NO_ASSIGNMENT).
 */
export function apiErrorCode(error: unknown): string | undefined {
  return extractCode(error)
}
