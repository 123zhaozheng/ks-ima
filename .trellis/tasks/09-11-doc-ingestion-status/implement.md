# 执行计划：文档摄入状态可视化 + 本地 worker

前置阅读：`prd.md`、`design.md`，以及 `implement.jsonl` 列出的 spec。
本地环境：`backend/run_server.py`（9016）、前端 9015、MinIO 9000、Postgres 5430。

## 步骤

### 1. 本地 dev worker
- [ ] `backend/run_server.py`：uvicorn 前用 `subprocess.Popen([sys.executable, "-m", "ima.workers.main"])`
      拉起 worker；`try/finally` 终止并等待其退出（超时则 kill）；worker 返回码异常时打印提示。
- 验证：`python backend/run_server.py` 后，上传文件能走到 `file_state='ready'`；
      队列 `ima_jobs.procrastinate_jobs` 出现并消费 `ima.ingestion.*`；Ctrl+C 后无残留 python 进程。

### 2. 前端状态映射工具
- [ ] 新增 `src/utils/ingestion-status.ts`：`fileStateView` / `stageLabel` / `jobStatusLabel` /
      `jobStatusColor`，未知值回退原字符串。
- 验证：新增 vitest 覆盖三态与未知值。

### 3. 列表状态呈现
- [ ] `src/components/KnowledgeList.vue`：caption 用 `fileStateView`（中文+图标+颜色）；
      删除 `pending` 锁图标与过时 tooltip；行菜单对所有非只读行可见。
- 验证：组件测试断言 `pending→处理中`（无锁、菜单在）、`ready→已就绪`、`failed→处理失败`，无英文枚举。

### 4. 详情 banner 中文化
- [ ] `src/components/DocPreview.vue`：`stage · status` 中文化 + 状态徽标；保留 取消/重试 逻辑。
- 验证：组件测试断言中文化文案与动作可见性。

### 5. 列表轮询
- [ ] `src/composables/use-knowledge.ts`：`useFolderContents` 在存在 pending file 行时
      `refetchInterval: 2000`，否则关闭。
- 验证：单测/手测（上传后列表自动翻到「已就绪」）。

### 6. 质量关卡（最后一轮全量）
- [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bun test`、`bunx vitest run` 全过。
- [ ] `rg "存储迁移"` 无残留（除历史 archive）。
- [ ] 手测：一条命令起 API+worker；上传 → 列表自动「已就绪」；失败文档可「重试」。
- [ ] 更新 spec：`file-upload-ingestion-contracts.md`（状态文案与轮询约定）。

## 回滚点

- 每步独立可回退；整体 `git revert`（无迁移、无持久化副作用）。

## 审查门

- 步骤 1 完成后确认 worker 生命周期正确（不残留、不抢 API 端口）。
- 步骤 6 全绿后方可报告完成；`git status` 确认未误动 scene-model-save 等无关改动。
