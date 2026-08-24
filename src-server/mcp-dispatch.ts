import { z } from 'zod'
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js'
import { WebStandardStreamableHTTPServerTransport } from '@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js'
import type { WorkspaceRole } from 'app/src-shared/utils/validators'

export type McpActor = {
  userId: string
  role: WorkspaceRole
  workspaceId: string
  folderRootId?: string | null
  mode: 'read' | 'readwrite'
  connectorId?: string
}

export type McpToolResult = {
  content: Array<{ type: 'text', text: string }>
  isError?: boolean
}

export type McpToolCall = (name: string, args: Record<string, unknown>) => Promise<McpToolResult>

export function attachKbTools(server: McpServer, actor: McpActor, call: McpToolCall) {
  const add = (
    name: string,
    description: string,
    inputSchema?: Record<string, z.ZodTypeAny>,
  ) => {
    if (inputSchema) {
      server.registerTool(name, { description, inputSchema }, async (args: Record<string, unknown>) =>
        call(name, args ?? {}),
      )
    } else {
      server.registerTool(name, { description }, async () => call(name, {}))
    }
  }

  add('kb_list_workspaces', 'List workspaces this connector can access')
  add('kb_list_dir', 'List a folder', { folderId: z.string().optional() })
  add('kb_get_tree', 'Shallow folder tree (capped depth)', {
    folderId: z.string().optional(),
    depth: z.number().optional(),
  })
  add('kb_search', 'Search parsed file chunks', {
    q: z.string(),
    limit: z.number().optional(),
    folderId: z.string().optional(),
    tags: z.array(z.string()).optional(),
  })
  add('kb_ask', 'Ask the knowledge base; returns answer plus citations', {
    question: z.string(),
    workspaceId: z.string().optional(),
    folderId: z.string().optional(),
    tags: z.array(z.string()).optional(),
  })
  add('kb_get_note', 'Get a markdown note', { id: z.string() })
  add('kb_get_file', 'Get parsed file text and a short-lived download URL', { id: z.string() })
  add('kb_list_tags', 'List tags in the workspace')

  if (actor.mode !== 'readwrite') return
  add('kb_mkdir', 'Create a folder', { parentId: z.string(), name: z.string() })
  add('kb_create_note', 'Create a markdown note', {
    parentId: z.string(),
    name: z.string(),
    text: z.string().optional(),
  })
  add('kb_update_note', 'Replace or append note text', {
    id: z.string(),
    text: z.string(),
    mode: z.string().optional(),
  })
  add('kb_upload_file', 'Upload a file (base64, max 8MB) and queue parse', {
    parentId: z.string(),
    name: z.string(),
    mimeType: z.string().optional(),
    contentBase64: z.string().optional(),
    text: z.string().optional(),
  })
  add('kb_move', 'Move notes, files, or folders', {
    id: z.string().optional(),
    ids: z.array(z.string()).optional(),
    to: z.string().optional(),
    parentId: z.string().optional(),
  })
  add('kb_set_tags', 'Set tags on a note or file', {
    id: z.string(),
    tags: z.array(z.string()),
  })
  add('kb_delete', 'Move notes, files, or folders to trash', {
    id: z.string().optional(),
    ids: z.array(z.string()).optional(),
  })
}

export async function dispatchMcp(actor: McpActor, req: Request, call: McpToolCall) {
  const server = new McpServer({ name: 'intranet-ima', version: '1.0.0' })
  attachKbTools(server, actor, call)
  const transport = new WebStandardStreamableHTTPServerTransport({
    enableJsonResponse: true,
    // Stateless per official SDK pattern: fresh server+transport per request.
    sessionIdGenerator: undefined,
  })
  await server.connect(transport)
  return transport.handleRequest(req)
}
