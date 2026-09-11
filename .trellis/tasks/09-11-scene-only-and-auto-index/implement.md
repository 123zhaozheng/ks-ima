# 执行计划：仅场景级模型 + 自动检索索引

前置阅读：`prd.md`、`design.md`、`implement.jsonl` 的 spec。
本地：`IMA_TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5430/app`。

## 步骤

### 1. 解析只走场景默认
- [ ] `model_governance.py` `_execution_target`：删 assignment 主查询与权威分支，改为直接解析 `scene_defaults`。
- [ ] `search.py` `_profile`：删 assignment 查询与 assigned 判定，直接用场景默认组合。
- 验证：postgres 用例 1。

### 2. 删除 KB 级分配
- [ ] 删服务方法 `assign/remove/list assignment`、路由、契约 DTO。
- [ ] 迁移 `..._0013_scene_only_models`：drop `ima.kb_profile_assignments`（downgrade 重建）。
- [ ] 重新生成 OpenAPI/前端类型；清理 `identity-client.ts`/任何引用。
- [ ] 更新/删除受影响测试。
- 验证：postgres 用例 4；`pytest tests/contract`。

### 3. 抽索引构建内核
- [ ] `search.py`：拆 `_build_index_core`（无授权）+ `build_vector_index`（owner 授权后调用）。
- 验证：既有索引测试不回退。

### 4. 摄入后自动建索引
- [ ] 新增索引构建任务（`infrastructure/tasks/`）或复用 `JobService` 入队；embed 成功后触发。
- [ ] 无模型/无 ready chunk → 跳过。
- 验证：postgres 用例 2。

### 5. reconcile 自愈
- [ ] `workers/main.py`：检测「ready chunk 但无 active 索引」的 KB → 入队索引构建。
- 验证：postgres 用例 3（构造 ready chunk 无索引）。

### 6. 质量关卡
- [ ] `cd backend && uv run ruff check . && uv run mypy src/ima`
- [ ] `IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres`（同步 conftest 计数）
- [ ] `bun run lint`、`bunx vue-tsc --noEmit`、`bun test`（OpenAPI 漂移）
- [ ] 更新 spec：`model-governance-contracts.md`、`search-grounded-ask-contracts.md`、`object-storage-ingestion-contracts.md`。

## 回滚点

- 迁移 down + `git revert`。索引可重建，无数据损失。

## 审查门

- 步骤 2 完成后确认无 `kb_profile_assignments` 残留且 OpenAPI 干净。
- 步骤 6 全绿且 `git status` 未误动其它任务文件后方可报告完成。
