import { expect, test, type Page } from '@playwright/test'

const fixture = `
<main>
  <label>Search <input aria-label="Search knowledge" /></label><button>Search</button>
  <div id="results"></div>
  <label>Ask <textarea aria-label="Ask grounded knowledge"></textarea></label>
  <button id="ask">Ask</button><button id="cancel">Cancel Ask</button>
  <div id="answer"></div><ol id="citations"></ol><div role="status"></div>
</main>
<script>
const results = document.querySelector('#results'), answer = document.querySelector('#answer'), citations = document.querySelector('#citations'), status = document.querySelector('[role=status]')
document.querySelector('button').onclick = async () => { const r = await fetch('/api/v1/workspaces/workspace-1/search?query=policy&mode=hybrid'); const data = await r.json(); results.textContent = data.items.map(x => x.title + ': ' + x.quote).join(' ') }
document.querySelector('#ask').onclick = async () => { const r = await fetch('/api/v1/workspaces/workspace-1/ask', { method: 'POST', body: JSON.stringify({ question: 'policy' }) }); const text = await r.text(); for (const block of text.trim().split('\\n\\n')) { const event = block.match(/event: (.+)/)?.[1], data = JSON.parse(block.match(/data: (.+)/)?.[1] || '{}'); if (event === 'citations') citations.innerHTML = data.citations.map(x => '<li>' + x.quote + '</li>').join(''); if (event === 'delta') answer.textContent += data.delta; if (event === 'completed') status.textContent = 'Completed'; } }
document.querySelector('#cancel').onclick = () => { status.textContent = 'Ask was cancelled'; document.querySelector('#cancel').hidden = true }
</script>`

async function install(page: Page) {
  await page.route('**/api/v1/workspaces/workspace-1/search?**', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items: [{ title: 'Policy', quote: 'Policy source' }] }) }))
  await page.route('**/api/v1/workspaces/workspace-1/ask', route => {
    if (route.request().headers()['x-test-cancel'] === '1') return route.fulfill({ contentType: 'text/event-stream', body: 'event: citations\ndata: {"citations":[{"quote":"Policy source"}]}\n\n' })
    return route.fulfill({ contentType: 'text/event-stream', body: 'event: citations\ndata: {"citations":[{"quote":"Policy source"}]}\n\nevent: delta\ndata: {"delta":"Grounded answer"}\n\nevent: completed\ndata: {}\n\n' })
  })
  await page.goto('/auth/sign-in')
  await page.setContent(fixture)
}

test.describe('grounded Ask desktop/mobile journey', () => {
  test('searches target sources and renders citations before progressive answer', async ({ page }, testInfo) => {
    await install(page)
    await page.getByLabel('Search knowledge').fill('policy')
    await page.getByRole('button', { name: 'Search' }).click()
    await expect(page.getByText('Policy source')).toBeVisible()
    await page.getByLabel('Ask grounded knowledge').fill('policy')
    await page.getByRole('button', { name: 'Ask', exact: true }).click()
    await expect(page.locator('#citations li')).toHaveText('Policy source')
    await expect(page.locator('#answer')).toHaveText('Grounded answer')
    await expect(page.getByRole('status')).toHaveText('Completed')
    await page.getByLabel('Ask grounded knowledge').fill('policy')
    await page.getByRole('button', { name: 'Ask', exact: true }).click()
    await page.getByRole('button', { name: 'Cancel Ask' }).click()
    await expect(page.getByRole('status')).toHaveText('Ask was cancelled')
    const viewport = await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)
    expect(viewport).toBe(true)
    await page.screenshot({ path: testInfo.outputPath('grounded-ask.png'), fullPage: true })
  })
})
