# 修复文档摄入取消/失败的终态卡死

## 背景

09-11 让上传→解析→向量化能真正跑通并在 UI 反映状态后，暴露出后端状态机的三处缺陷（已核实）：

1. **取消排队中的任务会永久卡死**：`StorageService.cancel()` 把任务置为 `cancel_requested`，
   但该状态**只能由正在运行的 worker 任务**落到 `cancelled`。若取消时任务还在 `queued`/`blocked`
   （worker 还没领走），就永远不会被处理 —— 既不会变 `cancelled`，也不在 `retry()` 允许的
   `failed/dead_letter/cancelled` 之内，于是**无任何出口**。
2. **没有 worker 时任务无人收敛**：`reconcile_ingestion` 只捡 `queued`/`retryable` 和租约过期的
   `running`，**不处理 `cancel_requested`**；worker 进程若未运行或中途死亡，取消请求就悬空。
3. **文档 `file_state` 永远不会变成 `failed`**：全仓库只有两处写 `documents.file_state` ——
   上传置 `pending`、embed 成功置 `ready`。**解析/切分/向量化失败（job 进入 `failed`/`dead_letter`）
   没有任何路径更新文档状态**，因此失败文档也永远显示"处理中"。
4. 取消后文档仍停在 `pending`，UI 持续显示"处理中"（子状态显示"取消中"却永不结束）。

## 目标

摄入任务进入终态（成功 / 失败 / 取消）时，**文档 `file_state` 与 UI 都反映终态**，且取消
**不会卡死**：排队中的任务立即取消，运行中的协作式取消，悬空的取消请求由 worker 收敛。

## 需求与约束

- 取消语义：
  - 处于 `queued`/`retryable`/`blocked` 的任务 → **直接置 `cancelled`**（无需 worker 介入）。
  - 处于 `running` 的任务 → 置 `cancel_requested`，由该任务协作式收尾为 `cancelled`（保持既有）。
  - 无任何可取消任务 → 409 `INGESTION_NOT_CANCELLABLE`（保持既有）。
- worker `reconcile_ingestion` 增加收敛：孤儿 `cancel_requested`（无有效租约）→ `cancelled`；
  过期的 `running`（租约失效）→ 走既有重排/收敛路径。
- 终态与文档状态：
  - 任一阶段任务进入 `failed`/`dead_letter` → 文档 `file_state='failed'`。
  - 取消完成（任务 `cancelled`）→ 文档 `file_state='failed'`（终态；不新增枚举，见"权衡"）。
  - `ready` 为最高优先，**一旦 `ready` 不被后续终态覆盖**。
  - `retry()` 成功后文档 `file_state` 回到 `pending`。
- **不新增数据库迁移**（理由见"权衡"）、不新增依赖、不改上传/下载/预览契约。
- 前端：`failed` 的列表/详情可读（详情对"取消"与"失败"分别措辞），终态不再轮询，提供重试。
- 不处理工作区中其它未提交任务（scene-model-save 等）的改动。

## 验收标准

- [ ] 上传后立刻取消（任务仍在 `queued`）→ 文档在数秒内进入终态，不再显示"处理中"。
- [ ] 取消"运行中"的任务 → 同样进入终态，不卡 `cancel_requested`。
- [ ] 模拟解析/向量化失败（如缺失对象）→ 文档 `file_state='failed'`，UI 显示"处理失败"。
- [ ] worker 未运行时的取消请求，在 worker 启动/reconcile 后能被收敛为终态。
- [ ] `ready` 文档不被任何后续终态写入覆盖。
- [ ] 终态文档提供「重试」，重试后文档回到"处理中"并可再次成功。
- [ ] 后端 postgres 用例覆盖：排队取消、运行取消、失败置 failed、reconcile 收敛、ready 不被覆盖、重试复位。
- [ ] `pytest -m postgres` 相关用例通过；前端 lint / `vue-tsc` / vitest 通过；spec 更新。

## 非目标

- 不新增 `file_state` 枚举值 / 迁移（理由见 design）。
- 不改上传票据、对象存储、向量维度等既有契约。
- 不重构任务队列框架（Procrastinate）。
- 不做取消的"撤回/继续"等额外交互。
