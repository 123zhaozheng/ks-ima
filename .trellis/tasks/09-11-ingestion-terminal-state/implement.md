# 执行计划：摄入终态与取消

前置阅读：`prd.md`、`design.md`，以及 `implement.jsonl` 的 spec。
本地验证：`IMA_TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5430/app`（共享 dev 库，测试自带清理）。
**注意：本任务不加迁移、不改 OpenAPI 契约、不动 scene-model-save 在途文件。**

## 步骤

### 1. 后端：取消分流（`application/storage.py`）
- [ ] `cancel()`：排队/阻塞（`queued/retryable/blocked`）→ 直接 `cancelled`；`running` → `cancel_requested`；
      若有终态任务且文档非 ready → `file_state='failed'`；两步无命中 → 409 `INGESTION_NOT_CANCELLABLE`。
- 验证：postgres 用例 1、2。

### 2. 后端：worker 终态写回（`infrastructure/tasks/ingestion.py`）
- [ ] 抽 `mark_document_terminal(conn, document_id)` → `file_state='failed' WHERE file_state <> 'ready'`。
- [ ] `failed()` 终态分支调用它；`cancelled()` 落 `cancelled` 时调用它。
- 验证：postgres 用例 3、5。

### 3. 后端：reconcile 收敛悬空取消（`workers/main.py`）
- [ ] 新增查询：`cancel_requested` 且无有效租约 → 直接 `cancelled` + `mark_document_terminal`（不 defer）。
- 验证：postgres 用例 4。

### 4. 后端：重试复位（`application/storage.py`）
- [ ] `retry()` 后 `documents.file_state='pending'`。
- 验证：postgres 用例 6。

### 5. 前端：终态措辞（`src/components/DocPreview.vue`）
- [ ] 顶部状态：含 failed/dead_letter → 处理失败；仅 cancelled → 已取消；ready → 已就绪。
- [ ] 确认重试按钮对 `cancelled/failed/dead_letter` 可见（既有条件）。
- 验证：vitest 断言。

### 6. 质量关卡（最后一轮全量）
- [ ] `cd backend && uv run ruff check . && uv run mypy src/ima`
- [ ] `IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres`（更新 `tests/conftest.py` 计数为 46+N）
- [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`
- [ ] 手测：上传→立即取消→文档数秒内终态；失败文档显示处理失败并可重试。
- [ ] 更新 spec：`object-storage-ingestion-contracts.md`（取消/终态语义）。

## 回滚点

- 每步独立可回退；整体 `git revert`（无迁移、无持久化副作用）。

## 审查门

- 步骤 1–3 完成后确认无路径遗留 `cancel_requested` 悬空（grep 用例断言）。
- 步骤 6 全绿且 `git status` 未误动 scene-model-save 在途文件后方可报告完成。
