import { describe, expect, test } from 'bun:test'

describe('Python identity bridge', () => {
  test('fails closed when no cookie or bridge configuration exists', async () => {
    const { getSession } = await import('./session')
    expect(await getSession(new Headers())).toBeNull()
  })

  test('never follows an untrusted public bridge URL', async () => {
    const previous = process.env.PYTHON_API_INTERNAL_URL
    process.env.PYTHON_API_INTERNAL_URL = 'https://public.example.invalid'
    const module = await import(`./session?untrusted=${Date.now()}`)
    expect(await module.getSession(new Headers({ cookie: 'ima_session=opaque' }))).toBeNull()
    process.env.PYTHON_API_INTERNAL_URL = previous
  })
})
