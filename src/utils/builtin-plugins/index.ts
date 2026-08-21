import type { PluginManifest } from 'src/stores/plugins'
import { mermaidPlugin } from './mermaid'
import { workspacePlugin } from './workspace'

export const builtinPlugins: PluginManifest[] = [mermaidPlugin, workspacePlugin]
