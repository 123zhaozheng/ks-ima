export async function openCreatedEntity<T>(
  load: () => Promise<T | null | undefined>,
  navigate: () => Promise<unknown>,
  options: {
    signal?: AbortSignal
    intervalMs?: number
    timeoutMs?: number
  } = {},
) {
  const { signal, intervalMs = 100, timeoutMs = 10_000 } = options
  const deadline = Date.now() + timeoutMs

  while (!signal?.aborted && Date.now() < deadline) {
    const entity = await load()
    if (entity) {
      if (!signal?.aborted) await navigate()
      return true
    }
    await new Promise(resolve => setTimeout(resolve, intervalMs))
  }
  return false
}
