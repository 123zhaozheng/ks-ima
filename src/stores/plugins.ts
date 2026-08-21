import { defineStore, acceptHMRUpdate } from 'pinia'
import { computed } from 'vue'
import { builtinPlugins } from 'src/utils/builtin-plugins'
import type { Avatar, McpTransport } from 'app/src-shared/utils/validators'
import type { PluginPrompt, PluginResource, PluginTool } from 'app/src-shared/utils/types'

export interface McpPluginManifest {
  id: string
  type: 'mcp'
  name: string
  description?: string
  avatar: Avatar
  transport: McpTransport
  requestTimeout?: number | null
  resetTimeoutOnProgress?: boolean | null
  keepAliveTimeout?: number | null
}
export interface BuiltinPluginManifest {
  id: string
  type: 'builtin'
  name: string
  description?: string
  avatar: Avatar
  tools: PluginTool[]
  resources: PluginResource[]
  prompts: PluginPrompt[]
  prompt?: string
}
export type PluginManifest = McpPluginManifest | BuiltinPluginManifest

export const usePluginsStore = defineStore('plugins', () => {
  const plugins = computed<PluginManifest[]>(() => builtinPlugins)
  return { plugins }
})

if (import.meta.hot) {
  import.meta.hot.accept(acceptHMRUpdate(usePluginsStore, import.meta.hot))
}
