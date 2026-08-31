import { expect, test, type Page } from '@playwright/test'
import { frontOrigin } from './environment'

/**
 * Knowledge base share-link journey (replaces the retired invitation flow):
 * the owner creates a knowledge base, issues a read-only share link from the
 * manage dialog, a second user joins through /join/:token and is restricted
 * to browsing, and the link stops working once revoked while users who
 * already joined keep their access. The second and third users run in
 * separate browser contexts so each keeps its own session.
 */

const ownerAccounts = {
  chromium: { email: 'e2e-oauth-chromium@example.com' },
  'mobile-chromium': { email: 'e2e-oauth-mobile-chromium@example.com' },
} as const
type ProjectName = keyof typeof ownerAccounts

// The joiner must be an account that never gains a knowledge base elsewhere
// in the suite (e2e-ordinary gets one in identity.pw.ts), so the auto-select
// of ids[0] after a fresh sign-in stays deterministic across workers.
const joinerAccount = { email: 'e2e-auditor@example.com', password: 'E2E-password-123' }
const outsiderAccount = { email: 'e2e-platform@example.com', password: 'E2E-password-123' }

function ownerFor(projectName: string) {
  const account = ownerAccounts[projectName as ProjectName]
  if (!account) throw new Error(`Unsupported sharing E2E project: ${projectName}`)
  return account
}

async function signIn(page: Page, email: string, password = 'E2E-password-123') {
  const response = await page.request.post('/api/v1/auth/sign-in', {
    data: { email, password },
    headers: { Origin: frontOrigin },
  })
  expect(response.ok()).toBeTruthy()
}

async function csrfHeaders(page: Page) {
  const response = await page.request.get('/api/v1/auth/csrf')
  const body = await response.json() as { csrfToken: string }
  return { Origin: frontOrigin, 'X-CSRF-Token': body.csrfToken }
}

interface KbSummary {
  id: string
  name: string
  role: 'owner' | 'editor' | 'viewer'
  owned: boolean
}

async function listKnowledgeBases(page: Page) {
  const response = await page.request.get('/api/v1/knowledge-bases')
  expect(response.ok()).toBeTruthy()
  return await response.json() as KbSummary[]
}

test.describe('knowledge base sharing journey', () => {
  test('read-only share link joins a second user, blocks writes, and stops new joins after revocation', async ({ page, browser }, testInfo) => {
    const owner = ownerFor(testInfo.project.name)
    await signIn(page, owner.email)
    const kbName = `E2E Shared KB ${Date.now()}`

    // Create the knowledge base through the API; the rail switcher that also
    // creates knowledge bases is hidden below the drawer breakpoint, and this
    // suite runs on the mobile project too.
    const created = await page.request.post('/api/v1/knowledge-bases', {
      data: { name: kbName },
      headers: await csrfHeaders(page),
    })
    expect(created.ok()).toBeTruthy()
    await page.goto('/kb')
    await expect(page.getByTestId('kb-tree-pane')).toBeVisible()
    await expect(page.getByRole('banner').getByText(kbName, { exact: true })).toBeVisible()

    // Issue a read-only share link from the manage dialog (owner only panels).
    await page.getByTestId('kb-manage').click()
    const dialog = page.getByTestId('kb-manage-dialog')
    await expect(dialog).toBeVisible()
    await expect(page.getByTestId('kb-rename-input')).toBeVisible()
    await expect(page.getByTestId('share-role-toggle')).toBeVisible()
    await page.getByTestId('share-link-create').click()
    await expect(page.getByTestId('share-link-new')).toBeVisible()
    const shareUrl = await page.getByTestId('share-link-url').locator('input').inputValue()
    expect(shareUrl).toContain('/join/')
    const token = new URL(shareUrl).pathname.split('/').filter(Boolean).pop()
    expect(token).toBeTruthy()

    // A user without membership cannot see the knowledge base before joining.
    const joinerContext = await browser.newContext({ baseURL: frontOrigin })
    const joiner = await joinerContext.newPage()
    try {
      await signIn(joiner, joinerAccount.email)
      expect((await listKnowledgeBases(joiner)).some(kb => kb.name === kbName)).toBe(false)

      // Opening /join/:token accepts the link automatically.
      await joiner.goto(`/join/${token}`)
      await expect(joiner.getByText('Joined knowledge base')).toBeVisible()
      await expect(joiner).toHaveURL(/\/kb/)
      await expect(joiner.getByTestId('kb-tree-pane')).toBeVisible()
      await expect(joiner.getByText('Read only').first()).toBeVisible()
      // Viewer role hides every write entry point.
      await expect(joiner.getByTestId('kb-new-folder')).toHaveCount(0)
      await expect(joiner.getByTestId('kb-new-note')).toHaveCount(0)
      await expect(joiner.getByTestId('kb-upload')).toHaveCount(0)

      // Membership is reported through the list with the viewer role.
      const joined = (await listKnowledgeBases(joiner)).find(kb => kb.name === kbName)
      expect(joined).toBeTruthy()
      expect(joined!.role).toBe('viewer')
      expect(joined!.owned).toBe(false)

      // Writes are refused at the API edge for viewers.
      const headers = await csrfHeaders(joiner)
      const noteCreate = await joiner.request.post(`/api/v1/folders/${joined!.id}/notes`, {
        data: { title: 'E2E Denied Note', markdown: 'must fail' },
        headers,
      })
      expect(noteCreate.status()).toBe(404)
      const folderCreate = await joiner.request.post(`/api/v1/knowledge-bases/${joined!.id}/folders`, {
        data: { parentId: joined!.id, name: 'E2E Denied Folder' },
        headers,
      })
      expect(folderCreate.status()).toBe(404)

      // Revoke the link; the row keeps showing it with a Revoked badge.
      await page.getByTestId('share-link-revoke').click()
      await page.getByRole('button', { name: 'Revoke', exact: true }).click()
      await expect(page.getByText('Link revoked')).toBeVisible()
      await expect(dialog.getByText('Revoked', { exact: true })).toBeVisible()

      // Revocation never touches existing members: the joiner keeps access in
      // the same context whose last selected knowledge base is the shared one.
      const stillMember = (await listKnowledgeBases(joiner)).find(kb => kb.name === kbName)
      expect(stillMember?.role).toBe('viewer')
      await joiner.goto('/kb')
      await expect(joiner.getByTestId('kb-tree-pane')).toBeVisible()
      await expect(joiner.getByRole('banner').getByText(kbName, { exact: true })).toBeVisible()
    } finally {
      await joinerContext.close()
    }

    // A third user can no longer join through the revoked link.
    const outsiderContext = await browser.newContext({ baseURL: frontOrigin })
    const outsider = await outsiderContext.newPage()
    try {
      await signIn(outsider, outsiderAccount.email)
      await outsider.goto(`/join/${token}`)
      await expect(outsider.getByTestId('join-error')).toBeVisible()
      expect((await listKnowledgeBases(outsider)).some(kb => kb.name === kbName)).toBe(false)
    } finally {
      await outsiderContext.close()
    }
  })
})
