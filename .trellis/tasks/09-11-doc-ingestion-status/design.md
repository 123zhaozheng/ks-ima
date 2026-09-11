# 技术设计：文档摄入状态可视化 + 本地 worker

## 现状（已核实）

- 后端状态权威：`ima.documents.file_state ∈ {pending, ready, failed}`（上传即 `pending`；
  `infrastructure/tasks/ingestion.py:347` 在 embed 全部成功后置 `ready`）。
  任务表 `ima.ingestion_jobs`：`stage ∈ {parse, chunk, embed}`、`status ∈ {queued, running,
  retryable, blocked, cancel_requested, succeeded, cancelled, failed, dead_letter}`。
- `GET /documents/{id}/ingestion` 返回 `IngestionStatusResponse{documentId, version, objectState,
  jobs[]}`，每个 job `{stage, status, completedUnits, totalUnits, errorCode, updatedAt}`。
- 列表 `GET /folders/{id}/contents` 的行（`ContentRow`）带 `fileState`（仅 file 行有值）。
- 前端：
  - `src/components/KnowledgeList.vue:34-48`：`pending` → 文案「存储迁移待完成」+ 锁图标
    （`v-else-if` 顺带隐藏了行菜单 → pending 文件无法删除）；`ready`/`failed` 直出英文。
  - `src/components/DocPreview.vue:144-166`：banner 输出 `${job.stage}: ${job.status}` 英文拼接；
    已有 取消（queued/running/retryable/cancel_requested）与 重试（failed/dead_letter/cancelled）。
  - `src/composables/use-knowledge.ts:64-70`：`useFolderContents` 无轮询；
    `useKnowledgeIngestion` 仅在有活跃任务时每 1.5s 轮询。
    `src/boot/vue-query.ts`：全局 `staleTime: 30_000`。
- 本地 dev：`backend/run_server.py` 只 `uvicorn.run("ima.main:app")`；
  `src/ima/workers/main.py` 是独立 worker（`queues=[diagnostic, ingestion]`，含 reconcile 卡住任务），
  README 记为 `uv run python -m ima.workers.main`。dev 未启动它 → 任务永不消费。

## 方案

### A. 本地 dev 起 worker

`backend/run_server.py` 在启动 uvicorn 前，用 `subprocess.Popen` 拉起 worker 子进程；
`try/finally` 中 `worker.terminate()`（必要时 `kill`）保证随 API 退出清理。

- 子进程继承 `run_server.py` 已 setdefault 的 `IMA_*` 环境（DB、origin、storage 均已在其中）。
- 命令：`[sys.executable, "-m", "ima.workers.main"]`。
- 不引入 reload 复杂度（dev 脚本本就不带 `--reload`）；worker 崩溃时打印其返回码，便于排查。
- 备选（未选）：① 在同一事件循环里内嵌 worker —— 与 uvicorn 争用、且违背"独立进程"的生产形态；
  ② 只在 README 记录手动启动 —— 不满足"开箱即用"。选子进程方案。

### B. 前端状态呈现

#### B1. 统一状态映射（新增 `src/utils/ingestion-status.ts`）

纯函数，供列表与详情共用，避免文案散落：

```ts
// file_state -> 列表/详情通用状态
export type DocStatusTone = 'pending' | 'ready' | 'failed'
export function fileStateView(state?: string | null): { tone: DocStatusTone; label: string; icon: string; color: string }
// pending -> 处理中 (spinner-ish icon, warning/grey)
// ready   -> 已就绪 (positive, check)   语义：已向量化，可被检索
// failed  -> 处理失败 (negative, error)
```

```ts
// ingestion job stage/status -> 中文（详情 banner）
export function stageLabel(stage: string): string      // parse=解析, chunk=切分, embed=向量化
export function jobStatusLabel(status: string): string // queued=排队中, running=处理中,
                                                       // retryable=重试中, blocked=等待中,
                                                       // cancel_requested=取消中, succeeded=已完成,
                                                       // cancelled=已取消, failed=处理失败, dead_letter=处理失败
export function jobStatusColor(status: string): string
```

未知值回退到原字符串（不崩、不隐藏）。

#### B2. `KnowledgeList.vue`

- 用 `fileStateView(item.fileState)` 渲染 caption：中文 + 图标 + 颜色（`text-caption` + `q-icon`）。
- **删除** `pending` 分支的锁图标与过时 tooltip；行菜单恢复对所有非只读行可见
  （把 `v-else-if` 的菜单改回独立 `v-if`），保证 pending 文档可删除。

#### B3. `DocPreview.vue` banner

- 把 `${stage}: ${status}` 换成中文：`解析 · 处理中`、`向量化 · 已完成` 等，
  前缀用整体状态徽标（已就绪/处理中/失败）。保留既有 取消/重试 动作与其触发条件。
- 当文档 `fileState === 'ready'` 时，banner 显示"已就绪，可被检索"，不再罗列任务。

#### B4. 轮询（`use-knowledge.ts`）

`useFolderContents` 增加条件轮询：列表中存在 `kind==='file' && fileState==='pending'` 时
`refetchInterval: 2000`，否则 `false`。这样上传后列表会自动从「处理中」翻到「已就绪」，
无需手动刷新。`useKnowledgeIngestion` 的既有轮询保持不变。

## 权衡与备选

- **备选 A：后端在列表接口里补充"向量化完成度/错误原因"** —— 当前 `fileState` 三态已足够表达
  用户所需（处理中/已就绪/失败）；详情页任务明细走既有 ingestion 接口。加字段属过度设计，弃。
- **备选 B：SSE/WebSocket 推送状态** —— 轮询足够且已有先例，弃。
- **备选 C：把 worker 塞进 API 进程** —— 违背进程边界，弃。

## 兼容与回滚

- 无后端/数据库改动；无接口变更（只消费既有字段）。
- 行为变化：`ready` 从英文变中文；`pending` 文案纠正；列表在 pending 时会轮询（请求量可控，
  2000ms 且仅在存在 pending 行时）。
- 回滚：`git revert` 即可（无迁移、无持久化状态）。

## 测试策略

- 单测（vitest）：
  - `src/utils/ingestion-status.ts` 的映射（含未知值回退）；
  - `KnowledgeList` 渲染：`pending`→「处理中」且**无**锁、菜单可见；`ready`→「已就绪」；
    `failed`→「处理失败」；不出现英文枚举。
  - `DocPreview` banner：阶段/状态中文化；失败显示「重试」、处理中显示「取消」。
- 静态：`bun run lint`、`bunx vue-tsc --noEmit`、`bun test`。
- 手动（dev）：`python backend/run_server.py` 一条命令起 API+worker；上传 docx → 列表自动变「已就绪」。
- 断言点：`file_state='ready'` 时列表文案为「已就绪」，且不再出现「存储迁移待完成」。
