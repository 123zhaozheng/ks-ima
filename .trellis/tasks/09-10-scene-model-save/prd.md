# 场景模型配置保存功能

## 背景

管理端「模型配置 → 场景配置」页（前任务 09-9 简化后的 UI）当前是占位：

- `src/admin/pages/ModelsPage.vue` 的 `saveSceneConfig` 是 TODO 存根，点击「保存」只弹「功能开发中」警告，不发任何请求。
- `sceneState` 初始化为全 null，从不回填当前生效值——页面上也看不到现状。
- 后端模型解析严格走「KB → workflow → capability profile 分配」（`ModelGovernanceService._execution_target`），无分配即拒绝（409 NO_ASSIGNMENT）。**不存在**「全局场景默认模型」这一层。

## 目标

为 5 个 workflow 场景（`grounded_ask` / `title_generation` / `summarization` / `embedding` / `reranking`）提供全局默认模型配置：

1. 管理员在场景配置页选择模型 → 点「保存」→ 真正持久化并生效。
2. 页面打开时回填当前默认值。
3. 运行时：KB 无分配时回退到场景默认模型；KB 有分配时行为不变（优先级：KB 分配 > 场景默认）。

## 需求与约束

- 保存时校验：模型必须存在、已启用（enabled）、能力（capability）与场景操作匹配（chat 场景选 chat 模型、embedding 场景选 embedding 模型、reranking 场景选 rerank 模型）；违规返回 422 与明确 code。
- 场景默认存于模型治理域内（capability profile 体系），不绕过既有版本化/审计机制。
- 所有变更写入 `ima.audit_events`。
- 仅 super_admin / platform_admin 可保存（与现有 admin 管理操作一致，mutate=True 门禁）。
- 前端沿用现有 `identityClient` 模式与错误提示风格；移除「功能开发中」占位逻辑。

## 验收标准

- [ ] 打开场景配置页，5 张卡片显示当前已配置的默认模型（未配置显示空）。
- [ ] 为「知识库问答」选一个 chat 模型并保存 → 200；刷新页面后回填为所选模型。
- [ ] 选未启用 / 能力不匹配的模型保存 → 4xx 明确错误，前端 toast 提示，状态不变。
- [ ] 一个无任何 KB profile 分配的知识库发起 grounded ask → 使用场景默认 chat 模型成功返回。
- [ ] 已有 KB 分配的知识库 → 仍用 KB 分配的 profile（回归不变）。
- [ ] 场景默认引用的模型后被禁用 → 运行时报 UNAVAILABLE（503），与 assignment 失效语义一致。
- [ ] `pytest -m postgres` 全绿；前端 `bun run lint`、`bun run test:unit` 通过。
- [ ] `POST/PUT` 操作在 `ima.audit_events` 有记录。

## 非目标

- 不做场景级的 temperature / system_prompt 等参数编辑（仍属 profile 高级能力，走既有 profile 管理流程）。
- 不做 per-KB 覆盖 UI（知识库详情页已有分配入口）。
- 不改 `grounded_ask` 卡片暴露 embedding/rerank 槽位（卡片只管 chat；向量化/重排序由各自场景卡负责）。
