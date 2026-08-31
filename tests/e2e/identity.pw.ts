import { expect, test, type Page } from '@playwright/test'
import { TOTP } from 'otpauth'
import { adminOrigin, frontOrigin } from './environment'

const identityProjectSuffixes = {
  chromium: { suffix: 'CHROMIUM', totpSecret: 'JBSWY3DPEHPK3PXP' },
  'mobile-chromium': { suffix: 'MOBILE', totpSecret: 'KRSXG5DSNFXGOIDB' },
} as const
type IdentityProjectName = keyof typeof identityProjectSuffixes

function isIdentityProjectName(projectName: string): projectName is IdentityProjectName {
  return Object.prototype.hasOwnProperty.call(identityProjectSuffixes, projectName)
}

function identityFixture(projectName: string) {
  if (!isIdentityProjectName(projectName)) {
    throw new Error(`Unsupported identity E2E project: ${projectName}`)
  }
  const project = identityProjectSuffixes[projectName]
  return {
    invite: {
      email: `e2e-invite-${projectName}@example.com`,
      token: `E2E-INVITATION-TOKEN-${project.suffix}`,
    },
    recovery: {
      email: `e2e-recovery-${projectName}@example.com`,
      code: `E2E-RECOVERY-CODE-${project.suffix}`,
    },
    totp: {
      email: `e2e-totp-${projectName}@example.com`,
      secret: project.totpSecret,
    },
  }
}

test.describe('local identity journeys', () => {
  const accounts = { ordinary: ['e2e-ordinary@example.com', 'E2E-password-123'], super: ['e2e-super@example.com', 'E2E-password-123'], platform: ['e2e-platform@example.com', 'E2E-password-123'], auditor: ['e2e-auditor@example.com', 'E2E-password-123'], disabled: ['e2e-disabled@example.com', 'E2E-password-123'] }
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
    await expect(page.getByRole('button', { name: /登录/ })).toBeVisible()
    await page.goto('/auth/sign-up')
    await expect(page.getByRole('button', { name: /注册/ })).toBeVisible()
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

  test('invited user accepts a single-use platform invitation and signs in', async ({ page }, testInfo) => {
    const fixture = identityFixture(testInfo.project.name)
    const password = 'E2E-invited-password-123'
    await page.goto(`/auth/accept-invite?token=${fixture.invite.token}`)
    await page.getByLabel('显示名称').fill('Accepted Invite')
    await page.getByLabel('密码').fill(password)
    await page.getByRole('button', { name: '接受邀请' }).click()
    await expect(page).toHaveURL(/auth\/sign-in/)
    const result = await login(page, fixture.invite.email, password)
    expect(result.status).toBe('authenticated')
    const replay = await page.request.post('/api/v1/auth/accept-invite', {
      data: { token: fixture.invite.token, password, displayName: 'Replay must fail' },
      headers: { Origin: frontOrigin },
    })
    expect(replay.status()).toBe(400)
  })

  test('ordinary user can use profile and session security on the settings page', async ({ page }) => {
    await page.goto('/auth/sign-in')
    await page.getByLabel('电子邮件').fill(accounts.ordinary[0])
    await page.getByLabel('密码').fill(accounts.ordinary[1])
    const signInResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/sign-in') && response.request().method() === 'POST')
    await page.getByRole('button', { name: /登录/ }).click()
    expect((await signInResponse).ok()).toBeTruthy()
    await expect.poll(async () => (await page.request.get('/api/v1/auth/session')).status()).toBe(200)
    // Settings is a single page: profile, security, and preferences sections.
    await page.goto('/settings')
    await expect(page.getByTestId('settings-profile')).toBeVisible()
    await expect(page.getByTestId('settings-security')).toBeVisible()
    await expect(page.getByTestId('settings-preferences')).toBeVisible()
    await expect(page.getByText('活跃会话', { exact: true })).toBeVisible()
  })

  test('super admin can manage roles, knowledge bases, and audit', async ({ page }) => {
    await login(page, accounts.super[0], accounts.super[1])
    await page.goto(`${adminOrigin}/users`)
    await expect(page.getByText('e2e-ordinary@example.com')).toBeVisible()
    await page.goto(`${adminOrigin}/knowledge-bases`)
    await expect(page.getByLabel('搜索知识库')).toBeVisible()
    await page.goto(`${adminOrigin}/audit`)
    await expect(page.getByRole('table')).toBeVisible()
    await expect(page.getByText('动作', { exact: true })).toBeVisible()
    await expect.poll(() => page.getByRole('row').count()).toBeGreaterThan(1)
  })

  test('knowledge base membership gates content access and platform roles do not imply it', async ({ page, browser }) => {
    await login(page, accounts.super[0], accounts.super[1])
    const kbName = `E2E Authorization ${Date.now()}`
    const create = await page.request.post('/api/v1/admin/knowledge-bases', {
      data: { name: kbName, initialOwnerUserId: 'e2e-ordinary-id' },
      headers: await csrfHeaders(page),
    })
    expect(create.ok()).toBeTruthy()
    const knowledgeBase = await create.json() as { id: string }
    expect((await page.request.get('/api/v1/knowledge-bases')).ok()).toBeTruthy()

    const ordinaryContext = await browser.newContext({ baseURL: frontOrigin })
    const ordinary = await ordinaryContext.newPage()
    try {
      await login(ordinary, accounts.ordinary[0], accounts.ordinary[1])
      const listed = await ordinary.request.get('/api/v1/knowledge-bases')
      expect(listed.ok()).toBeTruthy()
      const summary = JSON.stringify(await listed.json())
      expect(summary).toContain(kbName)
      expect(summary).toContain('"role":"owner"')
      const members = await ordinary.request.get(`/api/v1/knowledge-bases/${knowledgeBase.id}/members`)
      expect(members.ok()).toBeTruthy()
      const child = await ordinary.request.post(`/api/v1/knowledge-bases/${knowledgeBase.id}/folders`, {
        data: { parentId: knowledgeBase.id, name: 'E2E Private Folder' },
        headers: await csrfHeaders(ordinary),
      })
      expect(child.ok()).toBeTruthy()
    } finally {
      await ordinaryContext.close()
    }

    const platformContext = await browser.newContext({ baseURL: frontOrigin })
    const platform = await platformContext.newPage()
    try {
      await login(platform, accounts.platform[0], accounts.platform[1])
      // Platform capabilities govern the admin console only; without a
      // membership the folder tree is not even enumerable.
      const folders = await platform.request.get(`/api/v1/knowledge-bases/${knowledgeBase.id}/folders`)
      expect(folders.status()).toBe(404)
    } finally {
      await platformContext.close()
    }
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
    await expect(page.getByRole('table')).toBeVisible()
    await expect.poll(() => page.getByRole('row').count()).toBeGreaterThan(1)
    const response = await page.request.post('/api/v1/admin/knowledge-bases', { data: { name: 'auditor-must-not-create', initialOwnerUserId: 'e2e-ordinary-id' }, headers: await csrfHeaders(page) })
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

  test('TOTP challenge can be completed', async ({ page }, testInfo) => {
    const fixture = identityFixture(testInfo.project.name)
    await page.goto('/auth/sign-in')
    await page.getByLabel('电子邮件').fill(fixture.totp.email)
    await page.getByLabel('密码').fill('E2E-password-123')
    await page.getByRole('button', { name: /登录/ }).click()
    await expect(page.getByLabel('TOTP 代码')).toBeVisible()
    const code = new TOTP({ secret: fixture.totp.secret, algorithm: 'SHA1', digits: 6, period: 30 }).generate()
    await page.getByLabel('TOTP 代码').fill(code)
    const verifyResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/totp/verify') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '验证' }).click()
    expect((await verifyResponse).ok()).toBeTruthy()
  })

  test('recovery-code challenge can be completed exactly once', async ({ page }, testInfo) => {
    const fixture = identityFixture(testInfo.project.name)
    await page.goto('/auth/sign-in')
    await page.getByLabel('电子邮件').fill(fixture.recovery.email)
    await page.getByLabel('密码').fill('E2E-password-123')
    await page.getByRole('button', { name: /登录/ }).click()
    await page.getByRole('button', { name: '使用恢复码' }).click()
    await expect(page.getByLabel('恢复码')).toBeVisible()
    const code = fixture.recovery.code
    await page.getByLabel('恢复码').fill(code)
    const verifyResponse = page.waitForResponse(response => response.url().endsWith('/api/v1/auth/recovery/verify') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '验证' }).click()
    expect((await verifyResponse).ok()).toBeTruthy()
    const result = await login(page, fixture.recovery.email, 'E2E-password-123')
    expect(result.status).toBe('totp_required')
    if (!result.challenge) throw new Error('Recovery replay requires a fresh sign-in challenge')
    const second = await page.request.post('/api/v1/auth/recovery/verify', { data: { challenge: result.challenge, code }, headers: { Origin: frontOrigin } })
    expect(second.status()).toBe(401)
  })
})
