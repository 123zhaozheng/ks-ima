import { describe, expect, test } from 'vitest'
import { guessCapability } from '../../src/admin/model-catalog'

describe('guessCapability', () => {
  test.each([
    'bge-reranker-v2-m3',
    'bge-reranker-large',
    'jina-reranker-v2',
    'cross-encoder/ms-marco-MiniLM',
  ])('classifies %s as rerank', (modelId) => {
    expect(guessCapability(modelId)).toBe('rerank')
  })

  test.each([
    'bge-m3',
    'bge-large-zh-v1.5',
    'text-embedding-3-small',
  ])('classifies %s as embedding', (modelId) => {
    expect(guessCapability(modelId)).toBe('embedding')
  })

  test.each([
    'gpt-4o',
    'deepseek-chat',
  ])('classifies %s as chat', (modelId) => {
    expect(guessCapability(modelId)).toBe('chat')
  })
})
