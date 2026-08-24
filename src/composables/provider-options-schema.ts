import type { FullModel } from 'app/src-shared/queries'
import { t } from 'src/utils/i18n'
import type { InferSchema, ObjectSchema } from 'src/utils/types'
import { computed, type Ref } from 'vue'
import { mergeObjects } from 'src/utils/functions'

interface Rule<S extends ObjectSchema = ObjectSchema> {
  match: (model: FullModel) => boolean
  options: S
  exec: (options: InferSchema<S>) => { providerOptions: Record<string, any> }
}

function rule<S extends ObjectSchema>(value: Rule<S>): Rule<S> {
  return value
}

const rules = [
  rule({
    match: ({ name }) => /^gpt-5/.test(name),
    options: {
      reasoningEffort: {
        title: t('Reasoning Effort'),
        type: 'enum',
        options: ['low', 'medium', 'high', 'xhigh'] as const,
      },
    },
    exec: ({ reasoningEffort }) => ({
      providerOptions: { openaiCompatible: { reasoningEffort } },
    }),
  }),
  rule({
    match: ({ name }) => [
      'glm-5.1', 'glm-5', 'glm-4.7', 'glm-4.6', 'glm-4.5', 'glm-4.5v',
      'deepseek-v4-pro', 'deepseek-v4-flash',
    ].includes(name),
    options: {
      enableThinking: {
        title: t('Enable Thinking'),
        type: 'boolean',
        default: true,
      },
    },
    exec: ({ enableThinking }) => ({
      providerOptions: {
        openaiCompatible: enableThinking == null
          ? {}
          : { thinking: { type: enableThinking ? 'enabled' : 'disabled' } },
      },
    }),
  }),
]

export function useProviderOptionsSchema(model: Ref<FullModel | undefined>) {
  const activeRules = computed(() => rules.filter(rule => model.value && rule.match(model.value)))
  const schema = computed(() => {
    const matched = activeRules.value
    return matched.length ? mergeObjects(matched.map(rule => rule.options), 0) : null
  })
  function exec(options: Record<string, any>) {
    const results = activeRules.value.map(rule => rule.exec(options))
    return {
      providerOptions: mergeObjects(results.map(result => result.providerOptions), 1),
      providerTools: {},
    }
  }
  return { schema, exec }
}
