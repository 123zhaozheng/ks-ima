# 技术设计：摄入终态与取消

## 现状（已核实）

- 状态机：`ima.ingestion_jobs.status ∈ {blocked,queued,running,retryable,cancel_requested,
  cancelled,succeeded,failed,dead_letter}`；`ima.documents.file_state ∈ {pending,ready,failed}`（DB CHECK）。
- `StorageService.cancel()`（`application/storage.py:369`）只做一次
  `SET status='cancel_requested' WHERE status IN ('queued','running','retryable')`。
  而 `cancel_requested` **只在** worker 任务函数内的 `cancelled()`（`infrastructure/tasks/ingestion.py:61`）
  被落成 `cancelled`，且该函数仅在任务**已被 claim** 后调用。故排队中取消 = 永久悬空。
- `retry()`（`storage.py:324`）只接受 `failed/dead_letter/cancelled`；悬空的 `cancel_requested` 无出口。
- `documents.file_state` 仅两处写入：上传 `pending`（`storage.py:84`）、embed 成功 `ready`
  （`ingestion.py:347`）。**失败路径（parse/chunk/embed 的 `failed()`）从不更新文档状态。**
- `reconcile_ingestion`（`workers/main.py:36`）只挑 `queued/retryable` 与租约过期的 `running`，
  不处理 `cancel_requested`。

## 方案

### 后端

**1. `StorageService.cancel()` —— 排队即取消**
- 第一步：`UPDATE ... SET status='cancelled' WHERE document_id/version AND status IN ('queued','retryable','blocked')`。
  排队/阻塞任务无需 worker 即可终态化（`blocked` 是等待上游的 chunk/embed）。
- 第二步：`UPDATE ... SET status='cancel_requested' WHERE ... AND status='running'`（运行中协作式取消，保持既有）。
- 第三步：若任一任务已达终态（`cancelled`）且文档非 `ready` → `documents.file_state='failed'`。
- 两步都无命中 → 409 `INGESTION_NOT_CANCELLABLE`（保持既有语义）。

**2. worker 终态写回文档（`ingestion.py`）**
- 抽出 `mark_document_terminal(conn, document_id)`：`UPDATE ima.documents SET file_state='failed'
  WHERE id=:id AND file_state <> 'ready'`。
- `failed()` 写出 **终态** `failed`/`dead_letter` 时调用它（`retryable` 中间态不调用）。
- `cancelled()` 将 `cancel_requested` 落为 `cancelled` 时调用它。
- embed 成功仍置 `ready`（最高优先，`<> 'ready'` 守卫保证不被覆盖）。

**3. `workers/main.py` reconcile 收敛悬空取消**
- 在既有查询外，新增：`SELECT ... WHERE status='cancel_requested' AND (lease_expires_at IS NULL OR lease_expires_at < :now)`，
  直接 `UPDATE ... SET status='cancelled'` 并 `mark_document_terminal`（不 defer 任务，因为已无任务可跑）。
- 覆盖"取消时 worker 未运行/已死亡"的场景。

**4. `StorageService.retry()` 复位文档状态**
- 在既有把 parse 置 `queued`、chunk/embed 置 `blocked` 之后，加
  `UPDATE ima.documents SET file_state='pending', updated_at=:now WHERE id=:id`，
  使重试后 UI 回到"处理中"并能再次走到 `ready`。

### 前端

- `src/utils/ingestion-status.ts`：`fileStateView('failed')` 已有「处理失败」。不改映射；仅确认未知值仍回退。
- `src/components/DocPreview.vue`：终态措辞区分——
  - 任务含 `failed`/`dead_letter` → 顶部状态「处理失败」；
  - 任务含 `cancelled`（且无 failed）→ 顶部状态「已取消」；
  - 已就绪 → 「已就绪，可被检索」。
  - 既有「重试」按钮条件已含 `cancelled/failed/dead_letter`，无需改触发，仅确认可见。
- `src/components/KnowledgeList.vue`：`failed → 处理失败`（复用既有映射，不加迁移）。
- 轮询仅对 `pending`（既有），终态不轮询 —— 无需改动。

## 权衡与备选

- **备选 A：新增 `file_state='cancelled'` 枚举（含迁移）** —— UI 可精确区分"已取消"，但当前迁移头
  `20260910_0012` 是**另一个未提交任务的未跟踪文件**：链到它会在单独提交时引用未提交 revision，
  链到 `20260829_0011` 又会与其形成双头。**本任务不加迁移**，取消复用 `failed` 终态；
  列表统一显示「处理失败」，详情页按任务状态区分「已取消 / 处理失败」。
  待 scene-model-save 落地后，如需再补 `cancelled` 枚举，是一次独立的小迁移。
- **备选 B：取消时改文档为 `ready`** —— 语义错误（未完成解析却声称可检索），禁止。
- **备选 C：在 API 层同步把 `cancel_requested` 落终态** —— 只能覆盖排队任务，运行中仍需 worker 协作；
  按状态分流（排队直接、运行协作）才是正解。
- **选定**：状态分流 + worker 终态写回 + reconcile 收敛，无迁移。

## 兼容与回滚

- 无数据库迁移；无 OpenAPI 契约变化（字段与枚举不变，仅取值/时序变化）。
- 行为变化：取消排队任务立即终态；失败/取消文档从"永久处理中"变为 `failed` 终态并可重试。
- 回滚：`git revert`。

## 测试策略

- 后端（postgres 标记，新增 `tests/integration/test_postgres_ingestion_state.py`）：
  1. 排队取消：上传后（任务 `queued`）立即取消 → 所有任务 `cancelled`、文档 `failed`、**不残留 `cancel_requested`**。
  2. 运行取消：任务置 `running` 后取消 → 置 `cancel_requested`，worker `cancelled()` 落 `cancelled`、文档 `failed`。
  3. 失败置 failed：模拟终态失败（直接调用 `failed()` 或缺失对象）→ 文档 `failed`。
  4. reconcile 收敛：预置悬空 `cancel_requested`（无租约）→ reconcile 后为 `cancelled`、文档 `failed`。
  5. `ready` 不被覆盖：文档 `ready` 后触发终态写回 → 仍 `ready`。
  6. 重试复位：终态后 `retry()` → 文档 `pending`、parse `queued`。
  - 断言点：`ima.documents.file_state`、`ima.ingestion_jobs.status` 的具体取值。
- 前端：`ingestion-status` 映射单测（含 failed/cancelled 详情措辞）；`DocPreview` 终态按钮可见性。
- 静态：`ruff`、`mypy`、`bun run lint`、`bunx vue-tsc --noEmit`、`bunx vitest run`。
