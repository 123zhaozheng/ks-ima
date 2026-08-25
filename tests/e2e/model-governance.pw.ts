import { expect, test, type Page } from '@playwright/test'

const frontOrigin = 'http://127.0.0.1:9016'
const accounts = {
  ordinary: ['e2e-ordinary@example.com', 'E2E-password-123'],
  platform: ['e2e-platform@example.com', 'E2E-password-123'],
  auditor: ['e2e-auditor@example.com', 'E2E-password-123'],
}

async function login(page: Page, account: [string, string]) {
  const response = await page.request.post('/api/v1/auth/sign-in', {
    data: { email: account[0], password: account[1] },
    headers: { Origin: frontOrigin },
  })
  expect(response.ok()).toBeTruthy()
}

async function csrf(page: Page) {
  const response = await page.request.get('/api/v1/auth/csrf')
  const body = await response.json() as { csrfToken: string }
  return { Origin: frontOrigin, 'X-CSRF-Token': body.csrfToken }
}

test.describe('central model governance boundary', () => {
  test('ordinary users cannot enumerate infrastructure or execute an unassigned target', async ({ page }) => {
    await login(page, accounts.ordinary as [string, string])
    expect((await page.request.get('/api/v1/admin/model-gateways')).status()).toBe(403)
    const execution = await page.request.post('/api/v1/internal/model-governance/execute/chat', {
      data: {
        workspaceId: 'unassigned-model-workspace',
        workflow: 'grounded_ask',
        messages: [{ role: 'user', content: 'secret?' }],
      },
    })
    expect(execution.status()).toBe(404)
    expect(JSON.stringify(await execution.json().catch(() => ({})))).not.toContain('gatewaySecret')
  })

  test('auditor sees safe model metadata and no mutation controls', async ({ page }) => {
    await login(page, accounts.auditor as [string, string])
    const response = await page.request.get('/api/v1/admin/model-gateways')
    expect(response.ok()).toBeTruthy()
    const body = JSON.stringify(await response.json())
    expect(body).not.toContain('gatewaySecret')
    expect(body).not.toContain('fingerprint')
    const mutation = await page.request.post('/api/v1/admin/model-gateways', {
      data: { name: 'auditor-denied', baseUrl: 'https://gateway.internal', allowedCapabilities: ['chat'] },
      headers: await csrf(page),
    })
    expect(mutation.status()).toBe(403)
  })

  test('private resolver and execution routes are not public browser routes', async ({ page }) => {
    await page.goto('/auth/sign-in')
    expect([404, 405]).toContain((await page.request.get('/api/v1/internal/model-governance/resolve')).status())
    expect((await page.request.post('/api/v1/internal/model-governance/execute/chat', {
      data: {
        workspaceId: 'unassigned-model-workspace',
        workflow: 'grounded_ask',
        messages: [],
      },
    })).status()).toBe(404)
  })

  test('platform admin can open the governance surface', async ({ page }) => {
    await login(page, accounts.platform as [string, string])
    await page.goto('http://127.0.0.1:9017/models')
    await expect(page.getByText('Model governance')).toBeVisible()
    await expect(page.getByText('Gateways')).toBeVisible()
    await expect(page.getByText('Profiles')).toBeVisible()
  })
})
