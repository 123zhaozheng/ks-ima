import { expect, test, type Page } from '@playwright/test'
import { frontOrigin } from './environment'

/**
 * Three-pane knowledge base journey: folder tree | item list | preview pane.
 * Everything runs against the real API; each Playwright project uses its own
 * seeded OAuth account and knowledge base so runs stay isolated. Deleting a
 * note is immediate (no trash): confirm once and it is gone.
 */

const projectAccounts = {
  chromium: { email: 'e2e-oauth-chromium@example.com', kbId: 'e2e-oauth-chromium-kb' },
  'mobile-chromium': { email: 'e2e-oauth-mobile-chromium@example.com', kbId: 'e2e-oauth-mobile-chromium-kb' },
} as const
type ProjectName = keyof typeof projectAccounts

function accountFor(projectName: string) {
  const account = projectAccounts[projectName as ProjectName]
  if (!account) throw new Error(`Unsupported knowledge E2E project: ${projectName}`)
  return account
}

async function signIn(page: Page, email: string) {
  const response = await page.request.post('/api/v1/auth/sign-in', {
    data: { email, password: 'E2E-password-123' },
    headers: { Origin: frontOrigin },
  })
  expect(response.ok()).toBeTruthy()
}

test.describe('knowledge base desktop/mobile journey', () => {
  test('creates a folder and a note, previews, edits, pre-scopes Ask, and deletes the note', async ({ page }, testInfo) => {
    const account = accountFor(testInfo.project.name)
    await signIn(page, account.email)
    const suffix = Date.now()
    const folderName = `E2E Folder ${suffix}`
    const noteName = `E2E Note ${suffix}`
    const isDesktop = !testInfo.project.name.includes('mobile')

    await page.goto('/kb')
    await expect(page.getByTestId('kb-tree-pane')).toBeVisible()
    await expect(page.getByRole('treeitem', { name: 'All files' })).toBeVisible()
    await expect(page.getByTestId('kb-new-folder')).toBeEnabled()
    await expect(page.getByTestId('kb-new-note')).toBeEnabled()
    await expect(page.getByTestId('kb-upload')).toBeEnabled()
    // The preview pane defaults to collapsed; only the reopen rail shows.
    await expect(page.getByTestId('kb-preview-reopen')).toBeVisible()
    await expect(page.getByTestId('kb-preview-pane')).toHaveCount(0)

    // Create a folder from the tree pane header.
    // Quasar renders the q-input data-testid onto the native input itself.
    await page.getByTestId('kb-new-folder').click()
    await page.getByTestId('folder-name-input').fill(folderName)
    await page.getByTestId('folder-create-button').click()
    await expect(page).toHaveURL(/folderId=/)
    const folderId = new URL(page.url()).searchParams.get('folderId')
    expect(folderId).toBeTruthy()
    await expect(page.getByRole('treeitem', { name: folderName })).toBeVisible()
    await expect(page.getByText('Folder created')).toBeVisible()

    // Create a note inside the folder; it lands in the list and the editor.
    await page.getByTestId('kb-new-note').click()
    await page.getByTestId('note-title-input').fill(noteName)
    await page.getByTestId('note-create-button').click()
    await expect(page.getByText('Note created')).toBeVisible()
    await expect(page.locator('.kb-row').filter({ hasText: noteName })).toBeVisible()
    const preview = page.getByTestId('kb-preview-pane')
    await expect(preview).toBeVisible()
    await expect(preview.locator('.doc-preview-title input')).toHaveValue(noteName)

    // The fresh note opens in editor mode: type markdown, watch the render.
    const editor = preview.locator('.doc-preview-editor-input textarea')
    await expect(editor).toBeVisible()
    await editor.fill('# E2E heading\n\nBody paragraph for the preview.')
    await expect(preview.locator('.doc-preview-editor-render h1')).toHaveText('E2E heading')
    const save = page.getByRole('button', { name: 'Save', exact: true })
    await expect(save).toBeEnabled()
    await save.click()
    await expect(save).toBeDisabled()

    // "Ask about this document" pre-scopes the home composer to the note.
    await page.getByTestId('doc-ask-button').click()
    await expect(page).toHaveURL(/\/$/)
    const scopeChip = page.getByTestId('ask-scope-chip')
    await expect(scopeChip).toBeVisible()
    await expect(scopeChip).toContainText(noteName)

    // The upload dialog opens with its dropzone (object storage itself is not
    // provisioned in the e2e environment).
    await page.goto('/kb')
    await page.getByTestId('kb-upload').click()
    await expect(page.getByTestId('upload-dropzone')).toBeVisible()
    await page.getByRole('button', { name: 'Close', exact: true }).last().click()

    // Deletion is immediate: the list row menu confirms and removes the note.
    await page.goto(`/kb?folderId=${folderId}`)
    const row = page.locator('.kb-row').filter({ hasText: noteName })
    await expect(row).toBeVisible()
    await row.hover()
    await row.locator('.kb-row-menu').click()
    await page.getByTestId('row-delete-action').click()
    await page.getByRole('button', { name: 'Delete', exact: true }).click()
    await expect(page.getByText('Deleted')).toBeVisible()
    await expect(row).toHaveCount(0)

    if (isDesktop) {
      // Desktop rail navigation drives the same pages the drawer used to own.
      await expect(page.getByTestId('rail-nav-ask')).toBeVisible()
      await expect(page.getByTestId('rail-nav-history')).toBeVisible()
      await page.getByTestId('rail-nav-ask').click()
      await expect(page.getByTestId('ask-composer')).toBeVisible()
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
      expect(overflow).toBe(true)
      await page.screenshot({ path: testInfo.outputPath('knowledge-base.png'), fullPage: true })
    }
  })
})
