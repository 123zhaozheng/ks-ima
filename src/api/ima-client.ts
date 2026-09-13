import type { components } from 'src/api/generated/schema'
import { revalidateSession } from '../utils/identity-client'

type BuildInfo = components['schemas']['BuildInfo']
type ProblemDetails = components['schemas']['ProblemDetails']

export class IMAApiError extends Error {
  constructor(public readonly problem: ProblemDetails) {
    super(problem.detail)
    this.name = 'IMAApiError'
  }
}

export class IMAClient {
  constructor(private readonly origin = '') {}

  async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const headers = new Headers(init.headers)
    headers.set('Accept', 'application/json')
    if (init.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
    if (init.method && !['GET', 'HEAD'].includes(init.method)) {
      const csrf = document.cookie.split('; ').find(value => value.startsWith('ima_csrf='))?.split('=').slice(1).join('=')
      if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf))
    }
    const response = await fetch(`${this.origin}${path}`, { ...init, headers, credentials: 'include' })
    if (!response.ok) {
      const problem = await response.json() as ProblemDetails
      // Same mid-visit expiry handling as identityClient: re-check the session.
      if (response.status === 401) revalidateSession()
      throw new IMAApiError(problem)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  async getSystemInfo(signal?: AbortSignal): Promise<BuildInfo> {
    const response = await fetch(`${this.origin}/api/v1/system/info`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
      signal,
    })
    if (!response.ok) {
      const problem = await response.json() as ProblemDetails
      throw new IMAApiError(problem)
    }
    return response.json() as Promise<BuildInfo>
  }
}

export const imaClient = new IMAClient()
