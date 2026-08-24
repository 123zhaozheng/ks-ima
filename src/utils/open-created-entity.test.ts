import { describe, expect, test } from 'bun:test'
import { openCreatedEntity } from './open-created-entity'

describe('created entity navigation', () => {
  test('waits until the entity is visible before navigating', async () => {
    const calls: string[] = []
    const opened = await openCreatedEntity(
      () => {
        calls.push('visible')
        return Promise.resolve({ id: 'chat-1' })
      },
      () => {
        calls.push('navigate')
        return Promise.resolve()
      },
    )

    expect(opened).toBe(true)
    expect(calls).toEqual(['visible', 'navigate'])
  })

  test('does not navigate when the entity is still unavailable', async () => {
    let navigated = false
    const opened = await openCreatedEntity(
      () => Promise.resolve(undefined),
      () => {
        navigated = true
        return Promise.resolve()
      },
      { intervalMs: 0, timeoutMs: 1 },
    )

    expect(opened).toBe(false)
    expect(navigated).toBe(false)
  })

  test('does not navigate after the opening request is aborted', async () => {
    const controller = new AbortController()
    controller.abort()
    let navigated = false

    const opened = await openCreatedEntity(
      () => Promise.resolve({ id: 'chat-1' }),
      () => {
        navigated = true
        return Promise.resolve()
      },
      { signal: controller.signal },
    )

    expect(opened).toBe(false)
    expect(navigated).toBe(false)
  })

  test('retries until the entity becomes visible', async () => {
    let attempts = 0
    let navigated = false

    const opened = await openCreatedEntity(
      () => Promise.resolve(++attempts === 3 ? { id: 'chat-1' } : undefined),
      () => {
        navigated = true
        return Promise.resolve()
      },
      { intervalMs: 0 },
    )

    expect(opened).toBe(true)
    expect(attempts).toBe(3)
    expect(navigated).toBe(true)
  })
})
