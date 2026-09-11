# 技术设计：重排序能力识别

## 现状

`src/admin/model-catalog.ts`：
```ts
export function guessCapability(modelId: string): Capability {
  const value = modelId.toLowerCase()
  if (value.includes('embedding') || value.includes('bge')) return 'embedding'
  if (value.includes('rerank')) return 'rerank'
  return 'chat'
}
```
`bge` 先于 `rerank` → `bge-reranker-*` 被判为 embedding。
消费方：`ModelsPage.vue` 导入对话框（`guessCapability(name)`，`:783`）与维度自动填充（`:787`）。

## 方案

调整判定顺序与模式：

```ts
const RERANK_PATTERN = /rerank|reranker|cross-encoder|jina-reranker/
const EMBEDDING_PATTERN = /embedding|embed|bge(?!-reranker)|gte-|text-embedding|e5-|m3-/

export function guessCapability(modelId: string): Capability {
  const value = modelId.toLowerCase()
  if (RERANK_PATTERN.test(value)) return 'rerank'   // rerank 优先
  if (EMBEDDING_PATTERN.test(value)) return 'embedding'
  return 'chat'
}
```

要点：
- `rerank` 系列优先，覆盖 `rerank`/`reranker`/`cross-encoder`/`jina-reranker`。
- embedding 模式避免误伤：`bge-reranker` 已被 rerank 先行拦截；`bge-m3` 等仍走 embedding。
- `KNOWN_DIMENSIONS` 仅在 `capability === 'embedding'` 时使用（既有逻辑不变）。

## 测试策略

- 新增/扩展 `tests/`（vitest）对 `guessCapability` 的用例：rerank 家族、embedding 家族、chat；
  含 `bge-reranker-v2-m3`、`bge-reranker-large`、`bge-m3`、`text-embedding-3-small`、`gpt-4o`、
  `cross-encoder/ms-marco-MiniLM`。
- 静态：`bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`。

## 兼容与回滚

- 纯前端纯函数改动；`git revert` 即可。
