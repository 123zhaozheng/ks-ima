# 执行计划：重排序能力识别

## 步骤

1. [ ] `src/admin/model-catalog.ts`：`guessCapability` 改为 rerank 优先（模式见 design.md）。
2. [ ] 新增 vitest 覆盖 rerank/embedding/chat 三类的代表用例（含 `bge-reranker-v2-m3`、`bge-m3`）。
3. [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`。

## 回滚点

- 单函数改动，`git revert` 即可。

## 审查门

- 确认 `bge-m3` 仍为 embedding、`bge-reranker-*` 为 rerank、`gpt-4o` 为 chat。
