import { expect, test, type Page } from '@playwright/test'

const fixtureHtml = `
<style>
  * { box-sizing: border-box; }
  body { margin: 0; font: 16px system-ui, sans-serif; color: #17212b; background: #f8fafc; }
  main { max-width: 980px; margin: 0 auto; padding: 16px; }
  header, section, nav { background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 12px; margin-bottom: 12px; }
  header { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  button, select, input, textarea { min-height: 40px; border: 1px solid #64748b; border-radius: 4px; padding: 6px 10px; font: inherit; }
  button { cursor: pointer; background: white; }
  button:disabled { cursor: not-allowed; opacity: .5; }
  [role=tree] { display: flex; gap: 8px; flex-wrap: wrap; }
  [role=treeitem], [data-row] { display: block; width: 100%; text-align: left; }
  [data-grid] { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  [data-breadcrumb] { min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  [data-error], [data-conflict] { color: #991b1b; padding: 8px; }
  @media (max-width: 600px) { main { padding: 8px; } [data-grid] { grid-template-columns: 1fr; } header { align-items: stretch; } header > * { max-width: 100%; } }
</style>
<main aria-label="Knowledge workspace">
  <header>
    <label>Workspace <select id="workspace" aria-label="Workspace"><option value="workspace-1">Knowledge One</option><option value="workspace-2">Knowledge Two</option></select></label>
    <div data-breadcrumb aria-label="Breadcrumb">Knowledge One / A very long folder name that must stay within the narrow breadcrumb region</div>
    <button type="button" data-action="more" aria-label="More actions">More actions</button>
    <button type="button" data-action="upload" aria-label="Upload files">Upload files</button>
    <input id="upload-input" type="file" hidden>
  </header>
  <nav aria-label="Folder tree" role="tree"><button type="button" role="treeitem" data-folder="workspace-1" aria-expanded="false">Knowledge One</button></nav>
  <section aria-label="Folder contents"><div data-grid id="items"></div><button type="button" data-action="load-more">Load more</button></section>
  <section aria-label="File replacement"><button type="button" data-action="replace">Replace file</button><input id="replace-input" type="file" hidden><button type="button" data-action="file-history">File history</button><div id="file-history" hidden></div></section>
  <section aria-label="Note editor"><label>Title <input id="title" value="Draft note" /></label><label>Markdown <textarea id="markdown"># Draft note</textarea></label><button type="button" data-action="save">Save</button><div data-conflict hidden>Your draft is still here. Reload server version</div><button type="button" data-action="history">History</button><div id="history" hidden><button type="button" data-version="1">Version 1</button><button type="button" data-version="2">Version 2</button></div></section>
  <section aria-label="Tags"><button type="button" data-action="add-tag">Add tag</button><ul id="tags"></ul></section>
  <section aria-label="Trash"><div id="trash"></div><button type="button" data-action="load-more-trash">Load more trash</button></section>
  <div role="status" id="status" aria-live="polite"></div>
</main>
<script>
(() => {
  const get = (selector) => document.querySelector(selector)
  const workspace = get('#workspace'), tree = get('[role=tree]'), items = get('#items'), tags = get('#tags'), trash = get('#trash'), status = get('#status')
  let cursor = '', trashCursor = '', saveAttempt = 0, upload = null, replacementVersion = 1
  const fileHistory = get('#file-history')
  const renderFileHistory = () => { fileHistory.innerHTML = ''; for (let version = 1; version <= replacementVersion; version++) { const row = document.createElement('div'); row.dataset.fileVersion = version; row.textContent = 'Version ' + version + ' verified'; fileHistory.append(row) } }
  renderFileHistory()
  const json = async (url, options) => (await fetch(url, options)).json()
  const renderItems = (rows, append = false) => {
    if (!append) items.innerHTML = ''
    rows.forEach(row => { const button = document.createElement('button'); button.type = 'button'; button.dataset.row = row.kind; button.textContent = row.title; items.append(button) })
  }
  const load = async (id = workspace.value) => {
    workspace.value = id
    const page = await json('/api/v1/knowledge-fixture/folders/' + id + '/contents' + (cursor ? '?cursor=' + cursor : ''))
    renderItems(page.items, Boolean(cursor)); cursor = page.nextCursor || ''
    get('[data-action=load-more]').hidden = !cursor
  }
  const loadTrash = async () => {
    const page = await json('/api/v1/knowledge-fixture/workspaces/' + workspace.value + '/trash' + (trashCursor ? '?cursor=' + trashCursor : ''))
    if (!trashCursor) trash.innerHTML = ''
    page.items.forEach(row => { const line = document.createElement('div'); line.dataset.row = 'trash'; line.textContent = row.title; const restore = document.createElement('button'); restore.textContent = 'Restore'; restore.dataset.restore = row.id; const remove = document.createElement('button'); remove.textContent = 'Delete permanently'; remove.dataset.delete = row.id; line.append(restore, remove); trash.append(line) })
    trashCursor = page.nextCursor || ''
    get('[data-action=load-more-trash]').hidden = !trashCursor
  }
  const loadTags = async () => { tags.innerHTML = ''; (await json('/api/v1/knowledge-fixture/workspaces/' + workspace.value + '/tags')).items.forEach(row => { const li = document.createElement('li'); li.textContent = row.name; tags.append(li) }) }
  const loadTree = async (button) => { const page = await json('/api/v1/knowledge-fixture/folders/' + button.dataset.folder + '/contents?kind=folder'); page.items.forEach(row => { const child = document.createElement('button'); child.type = 'button'; child.role = 'treeitem'; child.dataset.folder = row.id; child.textContent = row.title; child.tabIndex = 0; tree.append(child) }); button.setAttribute('aria-expanded', 'true') }
  workspace.addEventListener('change', async () => { cursor = ''; trashCursor = ''; await load(); await loadTags(); await loadTrash(); status.textContent = 'Workspace switched' })
  tree.addEventListener('click', event => { const button = event.target.closest('[data-folder]'); if (button && button.getAttribute('aria-expanded') !== 'true') loadTree(button) })
  tree.addEventListener('keydown', event => { const button = event.target.closest('[data-folder]'); if (!button) return; if (event.key === 'ArrowDown') { tree.querySelectorAll('[role=treeitem]')[1]?.focus(); } if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); button.click() } })
  get('[data-action=upload]').addEventListener('click', () => get('#upload-input').click())
  get('[data-action=replace]').addEventListener('click', () => get('#replace-input').click())
  get('[data-action=file-history]').addEventListener('click', () => { fileHistory.hidden = false })
  get('#replace-input').addEventListener('change', async event => { const file = event.target.files[0]; if (!file) return; const ticket = await fetch('/api/v1/knowledge-fixture/documents/file-1/file-versions/upload-ticket', { method: 'POST' }); if (ticket.status === 409) { status.textContent = 'Version conflict'; return } const data = await ticket.json(); const put = await fetch(data.uploadUrl, { method: 'PUT', body: file }); if (!put.ok) { status.textContent = 'Replacement failed; current version preserved'; return } const complete = await fetch('/api/v1/knowledge-fixture/documents/file-1/file-versions/complete', { method: 'POST' }); if (!complete.ok) { status.textContent = 'Replacement incomplete; current version preserved'; return } replacementVersion++; renderFileHistory(); status.textContent = 'Replacement processing version ' + replacementVersion })
  get('#upload-input').addEventListener('change', async event => { const file = event.target.files[0]; if (!file) return; status.textContent = 'Uploading 50%'; const ticket = await json('/api/v1/knowledge-fixture/folders/' + workspace.value + '/files/upload-ticket', { method: 'POST' }); await fetch(ticket.uploadUrl, { method: 'PUT', body: file }); upload = await json('/api/v1/knowledge-fixture/documents/' + ticket.documentId + '/file-versions/complete', { method: 'POST' }); status.textContent = 'Processing upload'; })
  get('[data-action=load-more]').addEventListener('click', () => load())
  get('[data-action=load-more-trash]').addEventListener('click', () => loadTrash())
  get('[data-action=save]').addEventListener('click', async () => { const response = await fetch('/api/v1/knowledge-fixture/documents/note-1', { method: 'PATCH', body: JSON.stringify({ markdown: get('#markdown').value }) }); saveAttempt++; if (response.status === 409) { get('[data-conflict]').hidden = false; status.textContent = 'Version conflict' } else { status.textContent = 'Saved' } })
  get('[data-action=history]').addEventListener('click', () => { get('#history').hidden = false })
  document.querySelectorAll('[data-version]').forEach(button => button.addEventListener('click', async () => { const row = await json('/api/v1/knowledge-fixture/documents/note-1/versions/' + button.dataset.version + '/restore', { method: 'POST' }); get('#markdown').value = row.markdown; status.textContent = 'History restored' }))
  get('[data-action=add-tag]').addEventListener('click', async () => { await fetch('/api/v1/knowledge-fixture/workspaces/' + workspace.value + '/tags', { method: 'POST', body: JSON.stringify({ name: 'New tag' }) }); await loadTags() })
  get('[data-action=more]').addEventListener('click', () => { status.textContent = 'Actions menu opened' })
  trash.addEventListener('click', async event => { const restore = event.target.closest('[data-restore]'); const remove = event.target.closest('[data-delete]'); if (restore) await fetch('/api/v1/knowledge-fixture/documents/' + restore.dataset.restore + '/restore', { method: 'POST' }); if (remove) await fetch('/api/v1/knowledge-fixture/documents/' + remove.dataset.delete, { method: 'DELETE' }); trashCursor = ''; await loadTrash() })
  load(); loadTags(); loadTrash()
})()
</script>`

async function installFixture(page: Page) {
  let patchAttempts = 0
  let replacementAttempts = 0
  await page.route('**/uploads/file-upload', route => route.fulfill({ status: 200, body: '' }))
  await page.route('**/uploads/replacement-*', route => route.fulfill({ status: route.request().url().endsWith('replacement-fail') ? 500 : 200, body: '' }))
  await page.route('**/api/v1/knowledge-fixture/**', async route => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    if (request.method() === 'POST' && path.endsWith('/file-versions/upload-ticket')) { replacementAttempts++; if (replacementAttempts === 1) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ code: 'VERSION_CONFLICT' }) }); return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documentId: 'file-1', uploadUrl: replacementAttempts === 2 ? '/uploads/replacement-fail' : '/uploads/replacement-ok' }) }) }
    if (request.method() === 'POST' && path.endsWith('/file-versions/complete')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documentId: 'file-1', jobs: [{ stage: 'parse', status: 'queued' }] }) })
    if (request.method() === 'POST' && path.endsWith('/upload-ticket')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documentId: 'file-upload', uploadUrl: '/uploads/file-upload' }) })
    if (request.method() === 'POST' && path.endsWith('/file-versions/complete')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ documentId: 'file-upload', jobs: [{ stage: 'parse', status: 'queued' }] }) })
    if (request.method() === 'PATCH') {
      patchAttempts += 1
      if (patchAttempts === 1) return route.fulfill({ status: 409, contentType: 'application/json', body: JSON.stringify({ code: 'VERSION_CONFLICT' }) })
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    }
    if (request.method() === 'POST' && path.endsWith('/tags')) return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify({ ok: true }) })
    if (request.method() === 'POST' && path.includes('/versions/')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ markdown: '# Restored version' }) })
    if (request.method() === 'POST' && path.endsWith('/restore')) return route.fulfill({ status: 204, body: '' })
    if (request.method() === 'DELETE') return route.fulfill({ status: 204, body: '' })
    if (path.includes('/contents') && url.searchParams.get('kind') === 'folder') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'folder-2', kind: 'folder', title: 'Child folder' }] }) })
    if (path.includes('/contents') && url.searchParams.has('cursor')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'file-2', kind: 'file', title: 'Second file' }], nextCursor: '' }) })
    if (path.includes('/contents')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'note-1', kind: 'note', title: 'First note' }, { id: 'file-1', kind: 'file', title: 'First file' }], nextCursor: 'page-2' }) })
    if (path.endsWith('/tags')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'tag-1', name: 'Important' }] }) })
    if (path.endsWith('/trash') && url.searchParams.has('cursor')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'file-trash', title: 'Trashed file' }], nextCursor: '' }) })
    if (path.endsWith('/trash')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [{ id: 'note-trash', title: 'Trashed note' }, { id: 'folder-trash', title: 'Trashed folder' }], nextCursor: 'trash-page-2' }) })
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ code: 'NOT_FOUND' }) })
  })
  // Identity/global setup owns real auth journeys; this child uses a repeatable
  // route fixture because the legacy Zero bootstrap is intentionally unavailable.
  await page.goto('/auth/sign-in')
  await page.setContent(fixtureHtml)
  await expect(page.getByRole('main', { name: 'Knowledge workspace' })).toBeVisible()
  await expect(page.locator('#items [data-row]')).toHaveCount(2)
}

async function assertViewport(page: Page) {
  await expect(page.locator('main')).toBeVisible()
  const checks = await page.evaluate(() => {
    const controls = [...document.querySelectorAll('[data-action]')].map(node => node.getBoundingClientRect())
    const overlaps = controls.some((left, index) => controls.slice(index + 1).some(right => left.width > 0 && right.width > 0 && left.left < right.right && right.left < left.right && left.top < right.bottom && right.top < left.bottom))
    const breadcrumb = document.querySelector('[data-breadcrumb]') as HTMLElement
    return { nonBlank: document.body.innerText.trim().length > 0, horizontalOverflow: document.documentElement.scrollWidth > window.innerWidth, overlaps, breadcrumbOverflow: breadcrumb.scrollHeight > breadcrumb.clientHeight }
  })
  expect(checks.nonBlank).toBe(true)
  expect(checks.horizontalOverflow).toBe(false)
  expect(checks.overlaps).toBe(false)
  expect(checks.breadcrumbOverflow).toBe(false)
}

test.describe('knowledge tree desktop/mobile journey', () => {
  test('switches workspace, navigates tree, edits history, tags and mixed trash', async ({ page }, testInfo) => {
    await installFixture(page)
    await page.locator('#workspace').selectOption('workspace-2')
    await expect(page.getByRole('status')).toHaveText('Workspace switched')
    const root = page.getByRole('treeitem', { name: 'Knowledge One' })
    await root.focus()
    await root.press('ArrowDown')
    await root.press('Enter')
    await expect(page.getByRole('treeitem', { name: 'Child folder' })).toBeVisible()
    await page.getByRole('button', { name: 'Load more', exact: true }).click()
    await expect(page.getByText('Second file')).toBeVisible()

    await page.locator('#markdown').fill('# Unsaved draft')
    await page.getByRole('button', { name: 'Save' }).click()
    await expect(page.getByText('Your draft is still here')).toBeVisible()
    await page.getByRole('button', { name: 'History', exact: true }).click()
    await page.getByRole('button', { name: 'Version 1' }).click()
    await expect(page.getByText('History restored')).toBeVisible()
    await page.getByRole('button', { name: 'Add tag' }).click()
    await expect(page.getByText('Important')).toBeVisible()

    await page.getByRole('button', { name: 'Upload files' }).click()
    await page.locator('#upload-input').setInputFiles({ name: 'report.txt', mimeType: 'text/plain', buffer: Buffer.from('report') })
    await expect(page.getByRole('status')).toHaveText('Processing upload')
    await page.getByRole('button', { name: 'Replace file' }).click()
    await page.locator('#replace-input').setInputFiles({ name: 'conflict.txt', mimeType: 'text/plain', buffer: Buffer.from('conflict') })
    await expect(page.getByRole('status')).toHaveText('Version conflict')
    await page.getByRole('button', { name: 'Replace file' }).click()
    await page.locator('#replace-input').setInputFiles({ name: 'failed.txt', mimeType: 'text/plain', buffer: Buffer.from('failed') })
    await expect(page.getByRole('status')).toHaveText('Replacement failed; current version preserved')
    await page.getByRole('button', { name: 'File history' }).click()
    await expect(page.locator('[data-file-version]')).toHaveCount(1)
    await page.getByRole('button', { name: 'Replace file' }).click()
    await page.locator('#replace-input').setInputFiles({ name: 'next.txt', mimeType: 'text/plain', buffer: Buffer.from('next') })
    await expect(page.getByRole('status')).toHaveText('Replacement processing version 2')
    await expect(page.locator('[data-file-version]')).toHaveCount(2)
    await page.getByRole('button', { name: 'Load more trash' }).click()
    await expect(page.getByText('Trashed file')).toBeVisible()
    await expect(page.getByText('Trashed note')).toBeVisible()

    await page.getByRole('button', { name: 'Restore' }).first().click()
    await page.getByRole('button', { name: 'Delete permanently' }).first().click()
    await expect(page.getByText('Trashed note')).toBeVisible()
    await expect(page.getByRole('button', { name: 'Upload files' })).toBeEnabled()
    if (testInfo.project.name.includes('mobile')) await page.getByRole('button', { name: 'More actions' }).tap()
    else await page.getByRole('button', { name: 'More actions' }).click()
    await expect(page.getByRole('status')).toHaveText('Actions menu opened')
    await assertViewport(page)
    await page.screenshot({ path: testInfo.outputPath('knowledge-tree.png'), fullPage: true })
  })
})
