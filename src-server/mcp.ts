import { Hono } from 'hono'
import { cors } from 'hono/cors'
import { actorFromApiKey, type Actor } from './utils/permissions'
import { dispatchMcp } from './mcp-dispatch'
import {
  kbAsk,
  kbCreateNote,
  kbDelete,
  kbGetFile,
  kbGetNote,
  kbGetTree,
  kbListDir,
  kbListTags,
  kbMkdir,
  kbMove,
  kbSearch,
  kbSetTags,
  kbUpdateNote,
  kbUploadFile,
} from './kb/ops'

function textResult(data: unknown) {
  const isError = !!data && typeof data === 'object' && 'error' in data
  return {
    content: [{ type: 'text' as const, text: JSON.stringify(data, null, 2) }],
    ...(isError ? { isError: true } : {}),
  }
}

async function callTool(actor: Actor, name: string, args: Record<string, any>) {
  switch (name) {
    case 'kb_list_workspaces':
      return textResult([{ id: actor.workspaceId }])
    case 'kb_list_dir':
      return textResult(await kbListDir(actor, args.folderId || actor.folderRootId || actor.workspaceId) ?? { error: 'Not found' })
    case 'kb_get_tree':
      return textResult(await kbGetTree(
        actor,
        args.folderId || actor.folderRootId || actor.workspaceId,
        Number(args.depth ?? 2),
      ))
    case 'kb_search':
      return textResult(await kbSearch(actor, String(args.q ?? ''), {
        limit: args.limit == null ? undefined : Number(args.limit),
        folderId: args.folderId,
        tags: Array.isArray(args.tags) ? args.tags.map(String) : undefined,
      }))
    case 'kb_ask': {
      if (args.workspaceId && args.workspaceId !== actor.workspaceId) {
        return textResult({ error: 'Forbidden' })
      }
      return textResult(await kbAsk(actor, String(args.question ?? ''), {
        folderId: args.folderId,
        tags: Array.isArray(args.tags) ? args.tags.map(String) : Array.isArray(args.tagIds) ? args.tagIds.map(String) : undefined,
      }))
    }
    case 'kb_get_note':
      return textResult(await kbGetNote(actor, String(args.id)))
    case 'kb_get_file':
      return textResult(await kbGetFile(actor, String(args.id)))
    case 'kb_list_tags':
      return textResult(await kbListTags(actor))
    case 'kb_mkdir':
      return textResult(await kbMkdir(actor, String(args.parentId), String(args.name)))
    case 'kb_create_note':
      return textResult(await kbCreateNote(actor, String(args.parentId), String(args.name), args.text))
    case 'kb_update_note':
      return textResult(await kbUpdateNote(actor, String(args.id), String(args.text), args.mode))
    case 'kb_upload_file':
      return textResult(await kbUploadFile(actor, {
        parentId: String(args.parentId),
        name: String(args.name),
        mimeType: args.mimeType,
        contentBase64: args.contentBase64,
        text: args.text,
      }))
    case 'kb_move':
      return textResult(await kbMove(
        actor,
        Array.isArray(args.ids) ? args.ids.map(String) : [String(args.id)],
        String(args.to || args.parentId),
      ))
    case 'kb_set_tags':
      return textResult(await kbSetTags(actor, String(args.id), Array.isArray(args.tags) ? args.tags.map(String) : []))
    case 'kb_delete':
      return textResult(await kbDelete(
        actor,
        Array.isArray(args.ids) ? args.ids.map(String) : [String(args.id)],
      ))
    default:
      return { content: [{ type: 'text' as const, text: `Unknown tool: ${name}` }], isError: true }
  }
}

const app = new Hono()
  .use('*', cors({
    origin: '*',
    allowMethods: ['GET', 'POST', 'DELETE', 'OPTIONS'],
    allowHeaders: ['Content-Type', 'Authorization', 'mcp-session-id', 'Last-Event-ID', 'mcp-protocol-version'],
    exposeHeaders: ['mcp-session-id', 'mcp-protocol-version'],
  }))
  .all('/', async c => {
    const authz = c.req.header('authorization')
    if (!authz?.startsWith('Bearer ima_')) return c.json({ error: 'Unauthorized' }, 401)
    const actor = await actorFromApiKey(authz.slice('Bearer '.length).trim())
    if (!actor) return c.json({ error: 'Unauthorized' }, 401)
    return dispatchMcp(actor, c.req.raw, (name, args) => callTool(actor, name, args))
  })

export default app
