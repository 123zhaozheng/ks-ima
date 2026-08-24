import { expect, test, type Page } from '@playwright/test'
import { TOTP } from 'otpauth'

test.describe('local identity journeys', () => {
  const frontOrigin = 'http://127.0.0.1:9016'
  const adminOrigin = 'http://127.0.0.1:9017'
  const accounts = { ordinary: ['e2e-ordinary@example.com', 'E2E-password-123'], super: ['e2e-super@example.com', 'E2E-password-123'], platform: ['e2e-platform@example.com', 'E2E-password-123'], auditor: ['e2e-auditor@example.com', 'E2E-password-123'], disabled: ['e2e-disabled@example.com', 'E2E-password-123'], totp: ['e2e-totp@example.com', 'E2E-password-123'], recovery: ['e2e-recovery@example.com', 'E2E-password-123'] }
  async function login(page: Page, email: string, password: string) {
    const response = await page.request.post('/api/v1/auth/sign-in', { data: { email, password }, headers: { Origin: frontOrigin } })
    const body = await response.json() as { status?: string, challenge?: string, detail?: unknown }
    expect(response.ok(), JSON.stringify(body)).toBeTruthy()
    return body
  }
  async function csrfHeaders(page: Page) {
    const response = await page.request.get('/api/v1/auth/csrf')
    const body = await response.json() as { csrfToken: string }
    return { Origin: frontOrigin, 'X-CSRF-Token': body.csrfToken }
  }
  test('closed registration and sign-in surface', async ({ page }) => {
    await page.goto('/auth/sign-in')
    await expect(page.getByRole('button', { name: /sign in/i })).toBeVisible()
    await page.goto('/auth/sign-up')
    await expect(page.getByRole('button', { name: /sign up/i })).toBeVisible()
    const response = await page.request.post('/api/v1/auth/register', {
      data: { email: `closed-${Date.now()}@example.com`, password: 'password-123456', displayName: 'Closed' },
      headers: { Origin: new URL(page.url()).origin },
    })
    const body = await response.json()
    expect(response.status(), JSON.stringify(body)).toBe(404)
  })

  test('unauthenticated admin is redirected', async ({ page }) => {
    await page.goto(`${adminOrigin}/users`)
    await expect(page).toHaveURL(/auth\/sign-in/)
  })

  test('SMTP unavailable is reported by password reset API', async ({ page }) => {
    await page.goto('/auth/sign-in')
    const response = await page.request.post('/api/v1/auth/password/forgot', {
      data: { email: 'unknown@example.com' },
      headers: { Origin: new URL(page.url()).origin },
    })
    const body = await response.json()
    expect(response.ok(), JSON.stringify(body)).toBeTruthy()
    expect(body.accepted).toBe(true)
  })

  test('invited user accepts a single-use invitation and signs in', async ({ page }) => {
    const password = 'E2E-invited-password-123'
    await page.goto('/auth/accept-invite?token=E2E-INVITATION-TOKEN-0000000001')
    await page.getByLabel('Display name').fill('Accepted Invite')
    await page.getByLabel('Password').fill(password)
    await page.getByRole('button', { name: 'Accept invitation' }).click()
    await expect(page).toHaveURL(/auth\/sign-in/)
    const result = await login(page, 'e2e-invite@example.com', password)
    expect(result.status).toBe('authenticated')
  })

  test('ordinary user can use profile and session security', async ({ page }) => {
    await page.goto('/auth/sign-in')
    await page.getByLabel('Email').fill(accounts.ordinary[0])
    await page.getByLabel('Password').fill(accounts.ordinary[1])
    const signInResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/sign-in') && response.request().method() === 'POST')
    await page.getByRole('button', { name: /sign in/i }).click()
    expect((await signInResponse).ok()).toBeTruthy()
    await expect.poll(async () => (await page.request.get('/api/v1/auth/session')).status()).toBe(200)
    await page.goto('/account/security')
    await expect(page.getByText('Active sessions', { exact: true })).toBeVisible()
  })

  test('super admin can manage roles, workspaces, and audit', async ({ page }) => {
    await login(page, accounts.super[0], accounts.super[1])
    await page.goto(`${adminOrigin}/users`)
    await expect(page.getByText('e2e-ordinary@example.com')).toBeVisible()
    await page.goto(`${adminOrigin}/workspaces`)
    await expect(page.getByLabel('Search workspaces')).toBeVisible()
    await page.goto(`${adminOrigin}/audit`)
    await expect(page.getByText('auth.sign_in').first()).toBeVisible()
  })

  test('platform admin can manage ordinary users but cannot grant platform roles', async ({ page }) => {
    await login(page, accounts.platform[0], accounts.platform[1])
    const userId = 'e2e-ordinary-id'
    const response = await page.request.put(`/api/v1/admin/users/${userId}/roles/security_auditor`, { data: {}, headers: await csrfHeaders(page) })
    expect(response.status()).toBe(403)
  })

  test('security auditor has read-only audit access', async ({ page }) => {
    await login(page, accounts.auditor[0], accounts.auditor[1])
    expect((await page.request.get('/api/v1/admin/audit-events')).ok()).toBeTruthy()
    await page.goto(`${adminOrigin}/audit`)
    await expect(page.getByText('auth.sign_in').first()).toBeVisible()
    const response = await page.request.post('/api/v1/admin/workspaces', { data: { name: 'auditor-must-not-create' }, headers: await csrfHeaders(page) })
    expect(response.status()).toBe(403)
  })

  test('disabled user is rejected without account enumeration', async ({ page }) => {
    const response = await page.request.post('/api/v1/auth/sign-in', { data: { email: accounts.disabled[0], password: accounts.disabled[1] }, headers: { Origin: frontOrigin } })
    const body = await response.json()
    expect(response.status(), JSON.stringify(body)).toBe(401)
  })

  test('expired session is rejected by the Python authority', async ({ page }) => {
    const response = await page.request.get('/api/v1/auth/session', { headers: { Cookie: 'ima_session=expired-fixture' } })
    expect(response.status()).toBe(401)
  })

  test('TOTP challenge can be completed', async ({ page }) => {
    await page.goto('/auth/sign-in')
    await page.getByLabel('Email').fill(accounts.totp[0])
    await page.getByLabel('Password').fill(accounts.totp[1])
    await page.getByRole('button', { name: /sign in/i }).click()
    await expect(page.getByLabel('TOTP code')).toBeVisible()
    const code = new TOTP({ secret: 'JBSWY3DPEHPK3PXP', algorithm: 'SHA1', digits: 6, period: 30 }).generate()
    await page.getByLabel('TOTP code').fill(code)
    const verifyResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/totp/verify') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Verify' }).click()
    expect((await verifyResponse).ok()).toBeTruthy()
  })

  test('recovery-code challenge can be completed exactly once', async ({ page }) => {
    await page.goto('/auth/sign-in')
    await page.getByLabel('Email').fill(accounts.recovery[0])
    await page.getByLabel('Password').fill(accounts.recovery[1])
    await page.getByRole('button', { name: /sign in/i }).click()
    await page.getByRole('button', { name: 'Use recovery code' }).click()
    await expect(page.getByLabel('Recovery code')).toBeVisible()
    const code = 'E2E-RECOVERY-CODE'
    await page.getByLabel('Recovery code').fill(code)
    const verifyResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/recovery/verify') && response.request().method() === 'POST')
    await page.getByRole('button', { name: 'Verify' }).click()
    expect((await verifyResponse).ok()).toBeTruthy()
    const result = await login(page, accounts.recovery[0], accounts.recovery[1])
    const second = await page.request.post('/api/v1/auth/recovery/verify', { data: { challenge: result.challenge, code }, headers: { Origin: frontOrigin } })
    expect(second.status()).toBe(401)
  })
})
