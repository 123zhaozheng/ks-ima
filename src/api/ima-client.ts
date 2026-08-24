import type { components } from 'src/api/generated/schema'

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
