import { expect, test, type Page, type Route } from '@playwright/test'
import { frontOrigin } from './environment'

/**
 * The e2e environment has no model gateway and no grounded-Ask capability
 * profile, so the real `/ask` endpoint answers 409 NO_ASSIGNMENT. Like the
 * previous suite, this one drives the REAL app shell but mocks the knowledge
 * base ask/conversation endpoints at the network edge (`page.route`) using
 * the backend's SSE protocol (conversation/message/citations/delta/completed/
 * knowledge_gap/error frames). History is user-level now: the list endpoint
 * is `/conversations` and every row carries the knowledge base it lives in.
 * Citation previews still load REAL notes created through the real API, so
 * the highlight path runs on real data.
 */

const projectAccounts = {
  chromium: {
    email: 'e2e-oauth-chromium@example.com',
    kbId: 'e2e-oauth-chromium-kb',
    kbName: 'OAuth Knowledge Base (chromium)',
  },
  'mobile-chromium': {
    email: 'e2e-oauth-mobile-chromium@example.com',
    kbId: 'e2e-oauth-mobile-chromium-kb',
    kbName: 'OAuth Knowledge Base (mobile-chromium)',
  },
} as const
type ProjectName = keyof typeof projectAccounts

function accountFor(projectName: string) {
  const account = projectAccounts[projectName as ProjectName]
  if (!account) throw new Error(`Unsupported grounded Ask E2E project: ${projectName}`)
  return account
}

async function signIn(page: Page, email: string) {
  const response = await page.request.post('/api/v1/auth/sign-in', {
    data: { email, password: 'E2E-password-123' },
    headers: { Origin: frontOrigin },
  })
  expect(response.ok()).toBeTruthy()
}

async function csrfHeaders(page: Page) {
  const response = await page.request.get('/api/v1/auth/csrf')
  const body = await response.json() as { csrfToken: string }
  return { Origin: frontOrigin, 'X-CSRF-Token': body.csrfToken }
}

interface MockMessage {
  id: string
  role: 'user' | 'assistant'
  status: 'completed' | 'failed' | 'knowledge_gap'
  content: string
  sequence: number
}

interface MockConversation {
  id: string
  title: string
  messages: MockMessage[]
}

function sse(event: string, sequence: number, payload: Record<string, unknown>) {
  return `id: ${sequence}\nevent: ${event}\ndata: ${JSON.stringify(payload)}\n\n`
}

function messageRow(conversationId: string, message: MockMessage, createdAt: string) {
  return {
    id: message.id,
    role: message.role,
    status: message.status,
    content: message.content,
    sequence: message.sequence,
    version: 1,
    createdAt,
    updatedAt: createdAt,
    completedAt: message.status === 'completed' ? createdAt : null,
  }
}

function conversationDetail(kbId: string, kbName: string, conversation: MockConversation, createdAt: string) {
  return {
    id: conversation.id,
    kbId,
    kbName,
    title: conversation.title,
    lifecycle: 'active',
    version: 1,
    createdAt,
    updatedAt: createdAt,
    messages: conversation.messages.map(message => messageRow(conversation.id, message, createdAt)),
  }
}

/**
 * Installs the gateway mock. Question prefixes steer the stream:
 *   `fail:` — citations resolve but generation errors (covers retry)
 *   `gap:`  — the knowledge base has no answer (knowledge_gap event)
 */
async function installAskMock(page: Page, kbId: string, kbName: string, citation: { documentId: string, quote: string }) {
  const base = frontOrigin.replace(/\./g, '\\.') + `/api/v1/knowledge-bases/${kbId}`
  const createdAt = new Date().toISOString()
  const conversations = new Map<string, MockConversation>()
  let nextId = 1
  const id = (prefix: string) => `${prefix}-${kbId}-${nextId++}`

  function conversationRow(conversation: MockConversation) {
    return {
      id: conversation.id,
      kbId,
      kbName,
      title: conversation.title,
      lifecycle: 'active',
      version: 1,
      createdAt,
      updatedAt: createdAt,
    }
  }

  function streamEvents(conversation: MockConversation, assistant: MockMessage, mode: 'complete' | 'fail' | 'gap') {
    const basePayload = { conversationId: conversation.id, messageId: assistant.id }
    let sequence = 1
    let frames = sse('conversation', sequence++, { ...basePayload, conversation: conversationRow(conversation) })
    frames += sse('message', sequence++, { ...basePayload, status: 'pending' })
    if (mode === 'gap') {
      frames += sse('knowledge_gap', sequence++, { ...basePayload, answer: assistant.content, citations: [] })
      return frames
    }
    frames += sse('citations', sequence++, {
      ...basePayload,
      citations: [{
        rank: 1,
        quote: citation.quote,
        documentId: citation.documentId,
        documentVersion: 1,
        chunkDigest: 'e2e-chunk-digest',
        chunkOrdinal: 1,
        fileGeneration: null,
        score: 1,
      }],
    })
    if (mode === 'fail') {
      frames += sse('error', sequence++, { ...basePayload, code: 'NO_ASSIGNMENT' })
      return frames
    }
    for (const part of assistant.content.split('||')) {
      frames += sse('delta', sequence++, { ...basePayload, delta: part })
    }
    frames += sse('completed', sequence++, { ...basePayload, status: 'completed' })
    return frames
  }

  function appendExchange(body: { question?: string, conversationId?: string | null }, mode: 'complete' | 'fail' | 'gap') {
    const question = (body.question ?? '').trim()
    let conversation = body.conversationId ? conversations.get(body.conversationId) : undefined
    if (!conversation) {
      conversation = { id: id('conversation'), title: question.slice(0, 200), messages: [] }
      conversations.set(conversation.id, conversation)
    }
    const user: MockMessage = {
      id: id('message'),
      role: 'user',
      status: 'completed',
      content: question,
      sequence: conversation.messages.length + 1,
    }
    const answer = mode === 'complete'
      ? `The knowledge base policy requires two reviewers. [1]||Saved by the E2E suite.`
      : mode === 'gap'
        ? 'I could not find relevant information in your accessible knowledge.'
        : ''
    const assistant: MockMessage = {
      id: id('message'),
      role: 'assistant',
      status: mode === 'complete' ? 'completed' : mode === 'gap' ? 'knowledge_gap' : 'failed',
      content: answer.replace(/\|\|/g, ' '),
      sequence: conversation.messages.length + 2,
    }
    conversation.messages.push(user, assistant)
    return { conversation, user, assistant }
  }

  await page.route(`${frontOrigin}/api/v1/knowledge-bases/${kbId}/ask`, async (route: Route) => {
    const body = route.request().postDataJSON() as { question?: string, conversationId?: string | null }
    const question = (body.question ?? '').trim()
    const mode = question.startsWith('fail:') ? 'fail' : question.startsWith('gap:') ? 'gap' : 'complete'
    const { conversation, assistant } = appendExchange(body, mode)
    await route.fulfill({ contentType: 'text/event-stream', body: streamEvents(conversation, assistant, mode) })
  })

  await page.route(new RegExp(`^${base}/conversations/[^/]+/retry$`), async (route: Route) => {
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-2) ?? ''
    const conversation = conversations.get(conversationId)
    if (!conversation) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    // Retry replaces the failed assistant message in place, like the backend.
    const failed = [...conversation.messages].reverse().find(message => message.role === 'assistant' && message.status === 'failed')
    const assistant = failed ?? conversation.messages.at(-1)!
    assistant.status = 'completed'
    assistant.content = `Recovered after retry. [1]`
    await route.fulfill({ contentType: 'text/event-stream', body: streamEvents(conversation, assistant, 'complete') })
  })

  // User-level history: one list across every knowledge base of the user.
  await page.route(`${frontOrigin}/api/v1/conversations`, (route: Route) => {
    const items = [...conversations.values()].map(conversationRow)
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify({ items }) })
  })

  await page.route(new RegExp(`^${base}/conversations/[^/]+$`), (route: Route) => {
    const conversationId = new URL(route.request().url()).pathname.split('/').at(-1) ?? ''
    const conversation = conversations.get(conversationId)
    if (!conversation) return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    return route.fulfill({ contentType: 'application/json', body: JSON.stringify(conversationDetail(kbId, kbName, conversation, createdAt)) })
  })

  await page.route(new RegExp(`^${base}/messages/[^/]+/citations/\\d+$`), (route: Route) => {
    return route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        rank: 1,
        quote: citation.quote,
        documentId: citation.documentId,
        documentVersion: 1,
        chunkDigest: 'e2e-chunk-digest',
        chunkOrdinal: 1,
        fileGeneration: null,
        score: 1,
      }),
    })
  })

  return conversations
}

function composer(page: Page) {
  return page.locator('[data-testid=ask-composer] textarea')
}

async function askFromHome(page: Page, question: string) {
  const kbsLoaded = page.waitForResponse(response =>
    response.url().endsWith('/api/v1/knowledge-bases') && response.request().method() === 'GET')
  await page.goto('/')
  await expect(page.getByTestId('ask-composer')).toBeVisible()
  await kbsLoaded
  await composer(page).fill(question)
  await page.getByTestId('ask-send').click()
}

test.describe('grounded Ask desktop/mobile journey', () => {
  test('streams an answer from the home composer, opens the cited note, and saves it', async ({ page }, testInfo) => {
    const account = accountFor(testInfo.project.name)
    await signIn(page, account.email)
    const headers = await csrfHeaders(page)
    const noteTitle = `E2E Cited Note ${Date.now()}`
    const quote = 'The policy requires two independent reviewers.'
    const created = await page.request.post(`/api/v1/folders/${account.kbId}/notes`, {
      data: { title: noteTitle, markdown: `# Policy\n\n${quote}\n\nNothing else matters here.` },
      headers,
    })
    expect(created.ok()).toBeTruthy()
    const note = await created.json() as { id: string }
    await installAskMock(page, account.kbId, account.kbName, { documentId: note.id, quote })

    const question = `E2E question ${Date.now()}`
    await askFromHome(page, question)

    // The stream routes the home composer into a conversation view.
    await expect(page).toHaveURL(/\/ask\/conversation-/)
    await expect(page.getByTestId('conversation-title')).toHaveText(question)
    await expect(page.getByText(question, { exact: true }).first()).toBeVisible()
    const answer = page.getByTestId('assistant-answer').last()
    await expect(answer).toContainText('The knowledge base policy requires two reviewers.')
    const mark = page.getByTestId('citation-mark').last()
    await expect(mark).toBeVisible()
    await expect(mark).toHaveText('1')

    // Clicking the citation mark opens the cited document in the preview pane
    // and highlights the cited passage — no navigation away.
    await mark.click()
    const pane = page.getByTestId('citation-pane')
    await expect(pane).toBeVisible()
    await expect(pane.locator('.md-body h1')).toHaveText('Policy')
    await expect(pane.locator('mark')).toHaveText(quote)

    // Save the answer as a note into the knowledge base root folder.
    await page.getByTestId('save-as-note').last().click()
    const dialog = page.getByTestId('save-as-note-dialog')
    await expect(dialog).toBeVisible()
    await dialog.getByRole('option', { name: 'Whole knowledge base' }).click()
    await dialog.getByTestId('save-as-note-confirm').click()
    await expect(page.getByText('Note saved')).toBeVisible()

    // The saved note appears in the knowledge base list.
    await page.goto('/kb')
    await expect(page.locator('.kb-row').filter({ hasText: 'The knowledge base policy requires two reviewers.' }).first()).toBeVisible()
  })

  test('failed answers offer retry and the conversation lands in history with its knowledge base', async ({ page }, testInfo) => {
    const account = accountFor(testInfo.project.name)
    await signIn(page, account.email)
    const headers = await csrfHeaders(page)
    const noteTitle = `E2E Retry Note ${Date.now()}`
    const quote = 'Retry evidence kept in the cited note.'
    const created = await page.request.post(`/api/v1/folders/${account.kbId}/notes`, {
      data: { title: noteTitle, markdown: quote },
      headers,
    })
    expect(created.ok()).toBeTruthy()
    const note = await created.json() as { id: string }
    await installAskMock(page, account.kbId, account.kbName, { documentId: note.id, quote })

    const question = `fail: E2E failing question ${Date.now()}`
    await askFromHome(page, question)
    await expect(page).toHaveURL(/\/ask\/conversation-/)
    await expect(page.getByText('The answer failed to generate.').first()).toBeVisible()

    // Retry recovers the answer through the same stream contract.
    await page.getByTestId('answer-retry').first().click()
    await expect(page.getByTestId('assistant-answer').last()).toContainText('Recovered after retry.')

    // History lists the conversation with its knowledge base and reopens it.
    await page.goto('/history')
    const list = page.getByTestId('history-list')
    await expect(list).toBeVisible()
    const item = page.getByTestId('history-item').filter({ hasText: question }).first()
    await expect(item).toBeVisible()
    await expect(item).toContainText(account.kbName)
    await item.click()
    await expect(page).toHaveURL(/\/ask\/conversation-/)
    await expect(page.getByText(question, { exact: true }).first()).toBeVisible()
    await expect(page.getByTestId('assistant-answer').last()).toContainText('Recovered after retry.')
  })

  test('asks without matches surface the knowledge gap state', async ({ page }, testInfo) => {
    const account = accountFor(testInfo.project.name)
    await signIn(page, account.email)
    const headers = await csrfHeaders(page)
    const created = await page.request.post(`/api/v1/folders/${account.kbId}/notes`, {
      data: { title: `E2E Gap Note ${Date.now()}`, markdown: 'Unrelated content.' },
      headers,
    })
    expect(created.ok()).toBeTruthy()
    const note = await created.json() as { id: string }
    await installAskMock(page, account.kbId, account.kbName, { documentId: note.id, quote: 'unused' })

    await askFromHome(page, `gap: E2E gap question ${Date.now()}`)
    await expect(page).toHaveURL(/\/ask\/conversation-/)
    await expect(page.getByText('The knowledge base does not contain an answer to this question.').first()).toBeVisible()
  })
})
