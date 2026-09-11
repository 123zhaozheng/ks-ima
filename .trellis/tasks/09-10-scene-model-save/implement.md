# 执行计划：场景默认模型

前置：阅读 `prd.md`、`design.md`，以及 manifest 中列出的 spec。数据库连接（跑迁移/测试用）：
`IMA_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5430/app`（本地 docker `nyaai-dev-db-1`，已运行）。

## 步骤

### 1. 后端：迁移
- [ ] Alembic 新增 revision：建 `ima.scene_defaults`（含 workflow CHECK 枚举、FK、updated_at/by），提供 downgrade。
- 验证：`cd backend && IMA_DATABASE_URL=... uv run ima migrate` 成功；`\d ima.scene_defaults` 结构正确；`uv run ima migrate` 幂等重跑无错。

### 2. 后端：服务层
- [ ] `ModelGovernanceService.list_scene_defaults`
- [ ] `ModelGovernanceService.set_scene_default(actor_id, workflow, model_id|None)`（校验 → 找/建「场景默认」profile → draft→publish → upsert 指针 → 审计）
- [ ] `_execution_target` 回退分支（assignment 不存在 → 场景默认 → NO_ASSIGNMENT；默认失效 → UNAVAILABLE）
- 验证：新增/调整 `pytest -m postgres` 用例覆盖 design「测试策略」全部场景并通过；既有用例无回归。

### 3. 后端：API
- [ ] `model_governance_contracts.py`：`SceneDefaultItem` / `SceneDefaultUpdateRequest`（camelCase alias）
- [ ] `model_governance.py`：`GET /scene-defaults`、`PUT /scene-defaults/{workflow}`（mutate 门禁）
- 验证：起服务后 curl：GET 返回 5 个 workflow 的 items；PUT 合法模型 200、禁用模型 422、未登录 401。

### 4. 前端：client + 页面
- [ ] `identity-client.ts`：`listSceneDefaults` / `updateSceneDefault`
- [ ] `ModelsPage.vue`：`refresh()` 回填 `sceneState`；`saveSceneConfig` 真实调用（成功/失败 toast、按钮 loading）；删除 TODO 与「功能开发中」。
- 验证：`bun run lint`、`bun run test:unit` 通过；新增保存路径组件测试。

### 5. 端到端手测（验收对照 prd.md）
- [ ] 管理端：选模型保存 → 刷新回填。
- [ ] 用户端：无分配 KB 提问 → 用场景默认模型成功。
- [ ] 已分配 KB → 仍用 KB 分配（回归）。
- 验证手段：后端日志/审计表确认 `scene_default` 来源。

### 6. 质量关卡（最后一轮全量）
- [ ] `pytest -m postgres` 全绿；`ruff` / `mypy`（按仓库既有命令）；前端 lint + unit。
- [ ] 对照 `.trellis/spec/backend/model-governance-contracts.md` 复核解析语义未破坏。

## 回滚点

- 每步独立可回退；迁移 down + git revert 即可整体回滚（新表无既有数据依赖）。

## 审查门

- 步骤 3 完成后（后端 API 定型）自查一次契约与 spec 一致性。
- 步骤 6 通过后方可报告完成。
