import type { components } from 'src/api/generated/schema'
import { authenticatedFetch } from '../utils/identity-client'

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
    const response = await authenticatedFetch(`${this.origin}${path}`, init)
    if (!response.ok) {
      const problem = await response.json() as ProblemDetails
      throw new IMAApiError(problem)
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  async getSystemInfo(signal?: AbortSignal): Promise<BuildInfo> {
    const response = await authenticatedFetch(`${this.origin}/api/v1/system/info`, { signal })
    if (!response.ok) {
      const problem = await response.json() as ProblemDetails
      throw new IMAApiError(problem)
    }
    return response.json() as Promise<BuildInfo>
  }
}

export const imaClient = new IMAClient()
