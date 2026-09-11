# 修复重排序模型能力识别

## 背景

管理端从网关「拉取模型」时按模型 ID 推断能力（`src/admin/model-catalog.ts` 的 `guessCapability`）：

```ts
if (value.includes('embedding') || value.includes('bge')) return 'embedding'
if (value.includes('rerank')) return 'rerank'
```

`bge` 判断在前，导致 BAAI 的重排序模型（如 `bge-reranker-v2-m3`、`bge-reranker-large`）
因 ID 同时含 `bge` 与 `rerank` 而被**误判为向量化**，导入后在列表/导入对话框中不被标记为「重排序」，
管理员也无法据此正确配置场景默认 rerank 模型。

## 目标

按模型 ID 正确识别能力，重排序模型显示为「重排序」，不被误判为向量化。

## 需求与约束

- `rerank` 判定优先于 `embedding`/`bge`。
- 覆盖常见重排序命名：`rerank`、`reranker`、`bge-reranker*`、`cross-encoder*`、`-rerank-`、`jina-reranker` 等。
- 不误伤向量模型：`bge-m3`、`bge-large-zh`、`text-embedding-*` 仍判为向量化。
- 不误伤对话模型。
- 已知维度表（`KNOWN_DIMENSIONS`）不适用于 rerank（rerank 无维度），保持仅 embedding 填充。
- 不改后端能力枚举与契约。

## 验收标准

- [ ] `guessCapability('bge-reranker-v2-m3') === 'rerank'`；`('bge-reranker-large') === 'rerank'`；
      `('jina-reranker-v2') === 'rerank'`；`('cross-encoder/ms-marco') === 'rerank'`。
- [ ] `guessCapability('bge-m3') === 'embedding'`；`('text-embedding-3-small') === 'embedding'`；
      `('bge-large-zh-v1.5') === 'embedding'`。
- [ ] `guessCapability('gpt-4o') === 'chat'`；`('deepseek-chat') === 'chat'`。
- [ ] 前端单元测试覆盖上述用例；`bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run` 通过。

## 非目标

- 不改模型能力后端枚举/契约。
- 不做「按网关 /v1/models 返回元数据判断」的增强（网关多不返回该信息）。
- 不调整其它厂商/能力识别规则（除必要的 rerank 优先）。
