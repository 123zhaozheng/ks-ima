import { useQuasar } from 'quasar'
import ReauthDialog from 'src/components/ReauthDialog.vue'
import VerifyTotpDialog from 'src/components/VerifyTotpDialog.vue'
import { apiErrorCode } from 'src/utils/api-error'
import { revalidateSession, session } from 'src/utils/identity-client'

type MutationResult<T> = { data?: T, error?: { code?: string, message: string } }

/**
 * Wraps sensitive mutations that answer HTTP_401 for two different reasons:
 * a dead session, or a valid session past the recent-auth window. The 401
 * re-check distinguishes them: only a live session gets the password dialog
 * (with TOTP challenge support) and one retry; a dead session is left to the
 * useRequireLogin watchers, which redirect to sign-in.
 */
export function useRecentAuth() {
  const $q = useQuasar()

  function reauthenticate(): Promise<boolean> {
    return new Promise(resolve => {
      $q.dialog({ component: ReauthDialog, persistent: true })
        .onOk((challenge?: string) => {
          if (!challenge) {
            resolve(true)
            return
          }
          $q.dialog({ component: VerifyTotpDialog, componentProps: { challenge }, persistent: true })
            .onOk(() => resolve(true))
            .onCancel(() => resolve(false))
        })
        .onCancel(() => resolve(false))
    })
  }

  async function withRecentAuth<T>(action: () => Promise<MutationResult<T>>): Promise<MutationResult<T>> {
    let result = await action()
    if (!result.error || apiErrorCode(result.error) !== 'HTTP_401') return result
    await revalidateSession()
    if (!session.value.data) return result
    if (await reauthenticate()) result = await action()
    return result
  }

  return { reauthenticate, withRecentAuth }
}
