import { createHash } from 'node:crypto'
import { expect, test, type Page } from '@playwright/test'
import { frontOrigin } from './environment'

test.use({ trace: 'off' })

const projects = {
  chromium: 'chromium',
  'mobile-chromium': 'mobile-chromium',
} as const

function fixture(projectName: string) {
  if (!(projectName in projects)) throw new Error(`Unsupported OAuth E2E project: ${projectName}`)
  const name = projects[projectName as keyof typeof projects]
  return {
    clientId: `e2e-oauth-${name}`,
    clientName: `E2E OAuth Client (${name})`,
    email: `e2e-oauth-${name}@example.com`,
    workspaceId: `e2e-oauth-${name}-ws`,
    redirectUri: `${frontOrigin}/oauth/callback/${name}`,
  }
}

function authorizationRequest(projectName: string, state: string, scope: string) {
  const value = fixture(projectName)
  const verifier = `e2e-${projectName}-pkce-verifier-${'x'.repeat(64)}`
  const challenge = createHash('sha256').update(verifier).digest('base64url')
  const query = new URLSearchParams({
    response_type: 'code',
    client_id: value.clientId,
    redirect_uri: value.redirectUri,
    resource: `${frontOrigin}/mcp`,
    workspace_id: value.workspaceId,
    scope,
    state,
    code_challenge: challenge,
    code_challenge_method: 'S256',
    expires_at: new Date(Date.now() + 86400000).toISOString(),
  })
  return { value, verifier, url: `/oauth/authorize?${query}` }
}

async function login(page: Page, email: string) {
  const response = await page.request.post('/api/v1/auth/sign-in', {
    data: { email, password: 'E2E-password-123' },
    headers: { Origin: frontOrigin },
  })
  expect(response.status()).toBe(200)
  expect((await response.json() as { status: string }).status).toBe('authenticated')
}

async function assertNoOAuthStorage(page: Page, secrets: string[]) {
  const persisted = await page.evaluate(() => ({
    local: Object.entries(localStorage),
    session: Object.entries(sessionStorage),
  }))
  const serialized = JSON.stringify(persisted)
  for (const secret of secrets) expect(serialized).not.toContain(secret)
  expect(serialized).not.toMatch(/access_token|refresh_token|authorization_code/i)
}

test.describe('real OAuth consent desktop/mobile journey', () => {
  test('denies then approves a registered PKCE request and exchanges the code once', async ({ page }, testInfo) => {
    const project = fixture(testInfo.project.name)
    await login(page, project.email)

    const denied = authorizationRequest(
      testInfo.project.name,
      `deny-${testInfo.project.name}`,
      'mcp:workspaces:read',
    )
    await page.goto(denied.url)
    await expect(page).toHaveURL(/\/oauth\/consent\?/)
    await expect(page.getByRole('heading', { name: 'Connect agent' })).toBeVisible()
    await expect(page.getByText(project.clientName, { exact: true }).first()).toBeVisible()
    await expect(page.getByText(`${frontOrigin}/mcp`, { exact: true })).toBeVisible()
    await expect(page.getByText(project.redirectUri, { exact: true })).toBeVisible()
    await expect(page.getByText(project.workspaceId, { exact: true })).toBeVisible()
    await page.getByRole('button', { name: 'Deny', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`oauth/callback/${project.clientId.replace('e2e-oauth-', '')}`))
    let callback = new URL(page.url())
    expect(callback.searchParams.get('error')).toBe('access_denied')
    expect(callback.searchParams.get('state')).toBe(`deny-${testInfo.project.name}`)

    const approved = authorizationRequest(
      testInfo.project.name,
      `approve-${testInfo.project.name}`,
      'mcp:workspaces:read mcp:knowledge:read mcp:knowledge:write',
    )
    await page.goto(approved.url)
    const approvalLocation = new URL(page.url())
    if (approvalLocation.pathname.startsWith('/oauth/callback/')) {
      throw new Error(
        `Approval request returned OAuth error ${approvalLocation.searchParams.get('error') ?? 'missing_error'} for state ${approvalLocation.searchParams.get('state') ?? 'missing_state'}`,
      )
    }
    await expect(page).toHaveURL(/\/oauth\/consent\?/)
    await expect(page.getByText('This connection can change knowledge content.')).toBeVisible()
    await expect(page.getByText('Rotating refresh enabled')).toBeVisible()
    await page.getByRole('button', { name: 'Approve', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`oauth/callback/${testInfo.project.name}`))
    callback = new URL(page.url())
    const code = callback.searchParams.get('code')
    expect(code).toBeTruthy()
    expect(callback.searchParams.get('state')).toBe(`approve-${testInfo.project.name}`)
    expect(callback.searchParams.get('iss')).toBe(frontOrigin)

    // Leave the callback URL before any assertion can retain the one-time code in an artifact.
    await page.goto('/auth/sign-in')
    const exchange = await page.request.post('/oauth/token', {
      form: {
        grant_type: 'authorization_code',
        code: code!,
        client_id: project.clientId,
        redirect_uri: project.redirectUri,
        resource: `${frontOrigin}/mcp`,
        code_verifier: approved.verifier,
      },
    })
    expect(exchange.status()).toBe(200)
    const tokens = await exchange.json() as { access_token: string, refresh_token: string }
    expect(tokens.access_token).toBeTruthy()
    expect(tokens.refresh_token).toBeTruthy()

    const replay = await page.request.post('/oauth/token', {
      form: {
        grant_type: 'authorization_code',
        code: code!,
        client_id: project.clientId,
        redirect_uri: project.redirectUri,
        resource: `${frontOrigin}/mcp`,
        code_verifier: approved.verifier,
      },
    })
    expect(replay.status()).toBe(400)
    await assertNoOAuthStorage(page, [code!, tokens.access_token, tokens.refresh_token])
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  })

  test('shows an expired-session affordance without loading grant actions', async ({ page }, testInfo) => {
    const request = authorizationRequest(
      testInfo.project.name,
      `expired-${testInfo.project.name}`,
      'mcp:workspaces:read',
    )
    await page.goto(request.url.replace('/oauth/authorize?', '/oauth/consent?'))
    await expect(page.getByText('Your session expired. Sign in to continue.')).toBeVisible()
    await expect(page.getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', /\/auth\/sign-in/)
    await expect(page.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: 'Deny', exact: true })).toHaveCount(0)
    await assertNoOAuthStorage(page, [request.verifier])
  })
})
