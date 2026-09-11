# 文档摄入状态可视化与本地 ingestion worker

## 背景

用户在知识库上传文件后：

1. 列表里文件显示 **「存储迁移待完成」**，不知道是什么意思、也不知道是否处理成功。
2. 无法判断文档**是否已成功向量化（可检索）**。

排查结论（已核实）：

- **文案是历史遗留**：`src/components/KnowledgeList.vue:37` 把 `fileState === 'pending'`
  渲染为「存储迁移待完成」，来自早期"存储迁移"阶段（当时文件能力整体禁用）。
  现在 `pending` 的真实含义是 **文件已上传、但尚未完成解析+向量化**。旁边的锁图标与
  「存储迁移完成前，文件操作不可用」tooltip 同样过时（下载/预览其实可用）。
  且 `ready` / `failed` 会把**英文枚举原样**显示给用户。
- **看不到成功态的根本原因是本地没跑 ingestion worker**：
  `backend/run_server.py` 只启动 API（uvicorn）；消费解析/向量化任务的是独立进程
  `python -m ima.workers.main`（同时负责 reconcile 卡住的任务）。实测当前上传：
  对象 `verified`（135KB 成功）、文档 `file_state='pending'`、解析任务 `attempts=0` 从未执行、
  chunk 数为 0。后端 `file_state='ready'` 只在**全部 chunk 向量化成功**后才置位
  （`infrastructure/tasks/ingestion.py:347`），因此 `ready` 就等于"嵌入成功"。
- **UI 表达不足**：详情页 banner 只把英文 `stage: status` 拼成一行；列表不随处理进度刷新
  （`staleTime: 30s`，无轮询）。

## 目标

1. 本地 dev **开箱即用**：一条命令起 API + ingestion worker，上传的文件能真正走到"已就绪"。
2. 文档状态在 UI 上**清晰可读**：处理中 / 已就绪（可检索）/ 处理失败，含图标与颜色，不外露英文。
3. 处理中自动刷新，处理完成后自动变"已就绪"；失败可重试。

## 需求与约束

- 状态语义以后端为权威：`ima.documents.file_state ∈ {pending, ready, failed}`；
  任务 `stage ∈ {parse, chunk, embed}`、`status ∈ {queued, running, retryable, blocked,
  cancel_requested, succeeded, cancelled, failed, dead_letter}`。
  不得在前端伪造 `ready`（spec: `file-upload-ingestion-contracts.md`）。
- worker 以**独立进程**运行（与生产一致），dev 脚本负责随 API 一起拉起并随退出清理。
- 不改后端状态机与数据库；不新增依赖；不做大范围视觉改版，只做状态呈现。
- 保持既有契约：`upload` / 下载 / 预览 / 取消 / 重试 的现有行为不变；
  `pending` 文档仍可删除（当前因 `v-else-if` 被误隐藏，应恢复）。

## 验收标准

- [ ] 一条命令（`python run_server.py`）同时起 API 与 ingestion worker；退出时 worker 一并结束。
- [ ] 上传一个 docx/txt：列表状态从「处理中」自动变为「已就绪」，无需手动刷新。
- [ ] 文档 `file_state='ready'` 在 UI 上明确表达为"已就绪 / 可检索"（中文 + 图标/颜色）。
- [ ] 不再出现「存储迁移待完成」文案；不再向用户显示 `pending`/`ready`/`failed`/`parse`/`embed` 等英文枚举。
- [ ] 处理失败的文档显示"处理失败"，并提供「重试」；处理中提供「取消」。
- [ ] `pending` 文档的删除入口可用（不再被锁图标挡住）。
- [ ] 详情页 banner 用中文表达各阶段与状态（解析/切分/向量化 + 排队中/处理中/失败…）。
- [ ] 前端质量关卡通过：`bun run lint`、`bunx vue-tsc --noEmit`、`bun test`、`bunx vitest run`。
- [ ] 相关 spec 更新（`file-upload-ingestion-contracts.md` 等）。

## 非目标

- 不改上传/下载/预览/替换的流程与契约。
- 不引入 WebSocket/SSE 推送（用既有轮询即可）。
- 不重构知识库页面整体布局。
- 不处理"工作区里其它未提交改动"（scene-model-save 等）。
