import { IMAApiError } from 'src/api/ima-client'
import { t } from 'src/utils/i18n'

/**
 * Maps backend problem-details error codes to localized, actionable messages.
 * The keys are the stable `code` values raised by the backend (see
 * backend/src/ima/application/*.py). Values are i18n keys (English text) that
 * must be present in i18n/zh-CN.json and i18n/zh-TW.json.
 */
const CODE_MESSAGES: Record<string, string> = {
  FOLDER_NOT_FOUND: 'That folder could not be found. It may have been removed, or you may not have access to it.',
  DOCUMENT_NOT_FOUND: 'That item could not be found. It may have been removed, or you may not have access to it.',
  WORKSPACE_NOT_FOUND: 'That workspace could not be found. It may have been removed, or you may not have access to it.',
  USER_NOT_FOUND: 'That user could not be found.',
  MEMBER_NOT_FOUND: 'That member could not be found.',
  GROUP_NOT_FOUND: 'That group could not be found.',
  INVITATION_NOT_FOUND: 'That invitation could not be found. It may have expired or been revoked.',
  TAG_NOT_FOUND: 'That tag could not be found.',
  VERSION_NOT_FOUND: 'That version could not be found.',
  ASSIGNMENT_NOT_FOUND: 'No model assignment was found for this workspace.',
  STORAGE_UNAVAILABLE: 'File storage is temporarily unavailable. Please try again in a moment.',
  NO_ASSIGNMENT: 'No AI model has been assigned to this workspace yet. Ask a workspace or platform admin to assign one.',
  MODEL_UNAVAILABLE: 'The assigned AI model is not available. Ask an administrator to check the model gateway.',
  VERSION_CONFLICT: 'This item was changed by someone else. Refresh and try again.',
  CONTENT_TOO_LARGE: 'The content is too large to save.',
  BODY_TOO_LARGE: 'The file is too large to upload.',
  INVALID_TITLE: 'That title is not valid.',
  INVALID_CURSOR: 'The pagination cursor is invalid.',
  NOT_A_NOTE: 'Only notes support Markdown content.',
  CROSS_WORKSPACE: 'The destination is outside this workspace.',
  VALIDATION_ERROR: 'The request is invalid. Please check your input.',
  IDENTITY_ERROR: 'Your session is no longer valid. Please sign in again.',
  INTERNAL_ERROR: 'Something went wrong on our side. Please try again.',
  PLATFORM_FORBIDDEN: 'This action requires platform administrator rights. Ask your administrator for help.',
  HTTP_403: 'You do not have permission to do that.',
  HTTP_404: 'This action is not available right now.',
  HTTP_409: 'The request conflicts with the current state. Refresh and try again.',
  HTTP_429: 'Too many requests. Please wait a moment and try again.',
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
 * Returns a localized, user-facing message for an arbitrary thrown value.
 * Prefers a mapped problem-details code, then the problem detail, then a
 * generic fallback. Never leaks raw English backend strings into the zh UI.
 */
export function apiErrorMessage(error: unknown, fallback = 'Something went wrong. Please try again.'): string {
  const code = extractCode(error)
  if (code && CODE_MESSAGES[code]) return t(CODE_MESSAGES[code])
  return t(fallback)
}

/**
 * Returns the raw problem-details code for a thrown value, when available.
 * Useful for branching UI behavior (e.g. showing a "manage models" CTA only
 * when the failure is NO_ASSIGNMENT).
 */
export function apiErrorCode(error: unknown): string | undefined {
  return extractCode(error)
}
