import { IMA_BRIDGE_TIMEOUT_MS, PYTHON_API_INTERNAL_URL, IMA_BRIDGE_TOKEN } from '../utils/config'

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

const bridgeUrl = (() => {
  const value = PYTHON_API_INTERNAL_URL
  if (!value) return null
  try {
    const url = new URL(value)
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) return null
    const privateHost = url.hostname === 'localhost' || url.hostname === 'api' || url.hostname === 'python' || url.hostname.endsWith('.local') || /^(10\.|127\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(url.hostname)
    if (!privateHost) return null
    return `${url.origin}/api/v1/internal/session/introspect`
  } catch {
    return null
  }
})()

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
