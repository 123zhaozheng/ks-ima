import { db } from '../utils/db'
import { OPENAI_API_KEY, OPENAI_BASE_URL } from '../utils/config'
import { workspaceKbSettings } from './settings'

export interface GatewayModel {
  name: string
  baseURL: string
  apiKey: string
}

function resolveBaseURL(settings: Record<string, any> | null | undefined) {
  const url = settings?.baseURL as string | undefined
  if (!url || url.startsWith('/')) return OPENAI_BASE_URL || ''
  return url.replace(/\/$/, '')
}

export async function gatewayForModel(modelId: string | null | undefined): Promise<GatewayModel | null> {
  if (!modelId) return null
  const model = await db.query.model.findFirst({
    where: { id: modelId },
    with: { provider: true },
  })
  if (!model) return null
  const baseURL = resolveBaseURL(model.provider?.settings)
  if (!baseURL) return null
  const apiKey = (model.provider?.settings?.apiKey as string | undefined) || OPENAI_API_KEY || ''
  return { name: model.name, baseURL, apiKey }
}

export async function embeddingGateway(workspaceId: string) {
  const settings = await workspaceKbSettings(workspaceId)
  return gatewayForModel(settings.embeddingModelId)
}

export async function chatGateway(workspaceId: string) {
  const [root, globalSettings] = await Promise.all([
    db.query.entity.findFirst({
      where: { id: workspaceId },
      columns: { conf: true },
    }),
    db.query.globalSettings.findFirst(),
  ])
  const workspaceModelId = typeof root?.conf?.chatModelId === 'string'
    ? root.conf.chatModelId
    : null
  const workspaceGateway = await gatewayForModel(workspaceModelId)
  if (workspaceGateway) return workspaceGateway
  return gatewayForModel(globalSettings?.defaultChatModel)
}

export async function rerankGateway(workspaceId: string) {
  const settings = await workspaceKbSettings(workspaceId)
  return gatewayForModel(settings.rerankModelId)
}
