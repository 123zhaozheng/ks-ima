import { computed, type Ref } from 'vue'
import { usePluginsStore } from 'src/stores/plugins'
import type { PluginPrompt, PluginResource, PluginTool } from 'app/src-shared/utils/types'
import { engine } from 'src/utils/template-engine'
import { PluginsPromptTemplate } from 'src/utils/templates'

export type PluginStatus = 'ready'

export type Plugins = Record<string, {
  tools: PluginTool[]
  resources: PluginResource[]
  prompts: PluginPrompt[]
  status: PluginStatus
}>

export function usePlugins(ids: Ref<string[]>) {
  const pluginsStore = usePluginsStore()
  const manifests = computed(() => pluginsStore.plugins.filter(x => ids.value.includes(x.id)))
  const plugins = computed<Plugins>(() => Object.fromEntries(manifests.value.map(plugin => [plugin.id, {
    tools: plugin.tools,
    resources: plugin.resources,
    prompts: plugin.prompts,
    status: 'ready' as const,
  }])))
  const pluginsPrompt = computed(() => {
    if (!manifests.value.length) return ''
    return engine.parseAndRenderSync(PluginsPromptTemplate, {
      plugins: manifests.value,
    })
  })
  return {
    plugins,
    pluginsPrompt,
  }
}
