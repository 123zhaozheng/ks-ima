import type { BuiltinPluginManifest } from 'src/stores/plugins'
import { t } from '../i18n'
import { z } from 'zod'
import { client } from '../hc'
import { useWorkspaceStore } from 'src/stores/workspace'

const searchInputSchema = z.object({
  searches: z.array(z.object({
    q: z.string().describe('The search query'),
    types: z.array(z.enum(['chat', 'page', 'item'])).optional().describe('Types to search: chat, page (notes), item (files).'),
    limit: z.int().min(1).max(100).default(15),
  })),
})

export const workspacePlugin: BuiltinPluginManifest = {
  id: 'workspace',
  type: 'builtin',
  name: t('Knowledge Search'),
  avatar: { type: 'icon', icon: 'sym_o_manage_search', hue: 135 },
  description: t('Search notes and files in the current knowledge base. Always cite sources.'),
  prompt: `You are a knowledge-base librarian. Use the search tool before answering internal facts. If nothing is found, say the knowledge base does not contain it. Cite titles of notes/files you used.`,
  tools: [
    {
      name: 'search',
      inputSchema: z.toJSONSchema(searchInputSchema) as any,
      description: 'Search notes (page) and files (item) in the current workspace. Default searches notes and files.',
      async execute({ searches }: z.infer<typeof searchInputSchema>) {
        const workspaceStore = useWorkspaceStore()
        if (!workspaceStore.id) {
          throw new Error('Workspace is not initialized or selected')
        }

        const res = await Promise.all(searches.map(async args => {
          const result = await client.api.search.$post({
            json: {
              workspaceId: workspaceStore.id!,
              types: args.types ?? ['page', 'item'],
              q: args.q,
              limit: args.limit,
            },
          })
          const results = await result.json()
          return {
            q: args.q,
            results,
          }
        }))

        return {
          content: [{
            type: 'text',
            text: JSON.stringify(res, null, 2),
          }],
        }
      },
    },
  ],
  resources: [],
  prompts: [],
}
