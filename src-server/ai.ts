import { Hono } from 'hono'
import { z } from 'zod'
import { zValidator } from '@hono/zod-validator'
import { getSession } from './auth/session'
import { executeManagedChat, executeManagedLegacyChat } from './kb/model-governance'

const app = new Hono()

const messagesSchema = z.array(z.looseObject({
  role: z.string().optional(),
  content: z.union([
    z.string(),
    z.array(z.looseObject({ text: z.string().optional() })),
  ]),
})).min(1)

app.post('/chat/completions',
  zValidator('json', z.looseObject({
    // Kept for OpenAI-compatible clients during cutover. The server ignores it.
    model: z.string().optional(),
    stream: z.boolean().optional(),
    stream_options: z.object({ include_usage: z.boolean().optional() }).optional(),
    messages: messagesSchema,
    tools: z.array(z.looseObject({})).max(128).optional(),
  })),
  async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const workspaceId = c.req.header('Workspace-Id')
    if (!workspaceId) return c.json({ error: 'workspaceId not specified' }, 400)
    const body = c.req.valid('json')
    const stream = Boolean(body.stream)
    const managed = await executeManagedChat(
      workspaceId,
      'grounded_ask',
      body.messages,
      body.tools,
      stream,
    )
    if (managed.kind === 'target') {
      if (!managed.response) return c.json({ error: 'Model gateway is unavailable' }, 503)
      if (!managed.response.ok) return c.json({ error: 'Managed model capability is unavailable' }, 503)
      return new Response(managed.response.body, {
        status: 200,
        headers: { 'Content-Type': stream ? 'text/event-stream' : 'application/json' },
      })
    }
    if (managed.kind === 'denied') return c.json({ error: 'Assigned chat capability is unavailable' }, 503)
    const legacy = await executeManagedLegacyChat(
      workspaceId,
      'grounded_ask',
      body.messages,
      body.tools,
      stream,
    )
    if (legacy.kind !== 'unmigrated' || !legacy.response) {
      return c.json({ error: 'Assigned chat capability is unavailable' }, 503)
    }
    if (!legacy.response.ok) return c.json({ error: 'Legacy model capability is unavailable' }, 503)
    return new Response(legacy.response.body, {
      status: 200,
      headers: { 'Content-Type': stream ? 'text/event-stream' : 'application/json' },
    })
  })

app.post('/chat/titles',
  zValidator('json', z.object({ messages: messagesSchema })),
  async c => {
    const session = await getSession(c.req.raw.headers)
    if (!session) return c.json({ error: 'Unauthorized' }, 401)
    const workspaceId = c.req.header('Workspace-Id')
    if (!workspaceId) return c.json({ error: 'workspaceId not specified' }, 400)
    const body = c.req.valid('json')
    const managed = await executeManagedChat(workspaceId, 'title_generation', body.messages, undefined, false)
    if (managed.kind !== 'target' || !managed.response) {
      return c.json({ error: 'Assigned title capability is unavailable' }, managed.kind === 'unmigrated' ? 409 : 503)
    }
    if (!managed.response.ok) return c.json({ error: 'Assigned title capability is unavailable' }, 503)
    return new Response(managed.response.body, { status: 200, headers: { 'Content-Type': 'application/json' } })
  })

export default app
