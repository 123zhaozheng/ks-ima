import type { LanguageModel } from 'ai'
import type { Avatar } from 'app/src-shared/utils/validators'
import ky from 'ky'
import { createOpenAICompatible } from '@ai-sdk/openai-compatible'
import { t } from 'src/utils/i18n'
import type { InferSchema, ObjectSchema } from './types'
import { createOllama } from 'ollama-ai-provider-v2'

export interface ProviderType<S extends ObjectSchema> {
  label: string
  avatar: Avatar
  schema: S
  initialSettings?: Partial<InferSchema<S>>
  getModelList?: (settings: InferSchema<S>) => Promise<string[]>
  model: {
    language: (settings: InferSchema<S>, model: string) => LanguageModel
  }
}

function providerType<S extends ObjectSchema>(value: ProviderType<S>) {
  return value
}

const commonSchema = {
  baseURL: {
    type: 'string',
    format: 'url',
    title: t('API Address'),
    width: '225px',
  },
  apiKey: {
    type: 'string',
    title: 'API Key',
    format: 'password',
    width: '225px',
  },
} satisfies ObjectSchema

async function getModelList({ baseURL, apiKey }: InferSchema<typeof commonSchema>) {
  if (!baseURL) throw new Error(t('Please enter an intranet gateway address'))
  const { data } = await ky.get(`${baseURL}/models`, {
    headers: apiKey ? { Authorization: `Bearer ${apiKey}` } : {},
  }).json<{ data: Array<{ id: string }> }>()
  return data.map(model => model.id)
}

export const providerTypes = {
  openaiCompatible: providerType({
    label: 'OpenAI Compatible',
    avatar: { type: 'svg', name: 'openai', hue: 160 },
    schema: commonSchema,
    getModelList,
    model: {
      language: (settings, model) => createOpenAICompatible({
        name: 'openaiCompatible',
        includeUsage: true,
        supportsStructuredOutputs: true,
        ...settings,
        baseURL: settings.baseURL!,
      }).languageModel(model),
    },
  }),
  ollama: providerType({
    label: 'Ollama',
    avatar: { type: 'svg', name: 'ollama' },
    schema: {
      baseURL: {
        ...commonSchema.baseURL,
        placeholder: 'http://localhost:11434/api',
      },
    },
    model: {
      language: (settings, model) => createOllama(settings).languageModel(model),
    },
  }),
}

export type ProviderTypeKeys = keyof typeof providerTypes

export function getProviderType(type: string) {
  return providerTypes[type as ProviderTypeKeys] ?? providerTypes.openaiCompatible
}
