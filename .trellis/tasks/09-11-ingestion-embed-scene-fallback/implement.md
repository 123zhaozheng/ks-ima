# 执行计划：摄入向量化场景默认回退

前置阅读：`prd.md`、`design.md`，以及 `implement.jsonl` 的 spec。
本地验证：`IMA_TEST_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5430/app`。
**不加迁移、不改 OpenAPI、不动其它在途改动。**

## 步骤

### 1. 解析器补字段（`application/model_governance.py`）
- [ ] `_execution_target` 的 assignment SELECT 与 scene_default SELECT 均补选
      `m.version model_version, m.embedding_dimension`。
- [ ] 新增 `async def embedding_target(self, kb_id)` → `_execution_target(kb_id, Workflow.EMBEDDING, "embedding")`。
- 验证：既有用例不回归；新增 postgres 用例 1–4。

### 2. embed 任务改用访问器（`infrastructure/tasks/ingestion.py`）
- [ ] 删除 `ima.kb_profile_assignments` 直查；改用 `embedding_target`。
- [ ] 分流：`None`→`NO_ASSIGNMENT`；有 `reason`→该 reason；否则取 `model_id/model_version/embedding_dimension`。
- [ ] 保持 `kb_id` 缺失 → `DOCUMENT_NOT_FOUND`；维度/向量校验不变。
- 验证：postgres 用例；单测断言 embed 不再直查 assignments。

### 3. 质量关卡（最后一轮全量）
- [ ] `cd backend && uv run ruff check . && uv run mypy src/ima`
- [ ] `IMA_REQUIRE_POSTGRES=1 IMA_TEST_DATABASE_URL=... uv run pytest -m postgres`（若新增用例，同步 `tests/conftest.py` 计数）
- [ ] 手测（dev）：场景配置设全局 embedding 默认 → 无 KB 分配的知识库上传 → 文档 `ready`。
- [ ] 更新 spec：`object-storage-ingestion-contracts.md`（摄入与检索共享模型解析）。

## 回滚点

- 每步独立可回退；整体 `git revert`（无迁移、无持久化副作用）。

## 审查门

- 步骤 1 完成后确认 `_execution_target` 新字段不影响检索路径消费者。
- 步骤 3 全绿且 `git status` 未误动无关改动后方可报告完成。
