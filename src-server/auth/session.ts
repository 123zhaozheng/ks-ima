import { IMA_BRIDGE_TIMEOUT_MS, IMA_BRIDGE_TOKEN, privatePythonOrigin } from '../utils/config'

export type PythonSession = {
  user: {
    id: string
    email: string
    displayName: string
    imageUrl?: string | null
    platformRoles: string[]
    role?: string
    isActive: boolean
  }
}

const bridgeOrigin = privatePythonOrigin()
const bridgeUrl = bridgeOrigin ? `${bridgeOrigin}/api/v1/internal/session/introspect` : null

/** The one browser-session adapter used by every legacy Bun route. */
export async function getSession(headers: Headers): Promise<PythonSession | null> {
  if (!bridgeUrl || !IMA_BRIDGE_TOKEN) return null
  const cookie = headers.get('cookie')
  if (!cookie) return null
  const forwarded = new Headers({ cookie })
  const userAgent = headers.get('user-agent')
  if (userAgent) forwarded.set('user-agent', userAgent.slice(0, 512))
  forwarded.set('x-ima-bridge-token', IMA_BRIDGE_TOKEN)
  try {
    const response = await fetch(bridgeUrl, {
      method: 'POST',
      headers: forwarded,
      redirect: 'error',
      signal: AbortSignal.timeout(Math.max(250, IMA_BRIDGE_TIMEOUT_MS)),
    })
    if (!response.ok) return null
    const payload = await response.json() as PythonSession
    if (!payload.user?.id || !payload.user.isActive) return null
    return payload
  } catch {
    return null
  }
}
