# 技术设计：摄入向量化使用场景默认回退

## 现状（已核实）

- `ModelGovernanceService._execution_target(kb_id, workflow, operation)`（`application/model_governance.py:2024`）
  是唯一带场景默认回退的解析器：先查 `kb_profile_assignments`（有 assignment 即权威，即使 join 不通也返回
  `reason='UNAVAILABLE'`）；无 assignment 行时查 `scene_defaults[workflow]`，用同样的
  profile/version/model/gateway/health JOIN 解析；都无 → 返回 `None`。
- 它的两个 SELECT 目前**只取** `m.id model_id, m.remote_name, m.capability, m.enabled, m.validated`，
  **不含** `m.version` 与 `m.embedding_dimension`。
- `managed_embeddings`（`:2231`）调用 `_execution_target(kb_id, EMBEDDING, "embedding")`，已含回退。
- `infrastructure/tasks/ingestion.py` 的 `embed` 任务**绕过**它，直接
  `SELECT ... FROM ima.kb_profile_assignments a JOIN ... JOIN ima.governed_models m ...`（`:296`）
  取 `m.id, m.version, m.embedding_dimension`；`if not model` → `NO_ASSIGNMENT` 失败。

## 方案

### 1. 让解析器暴露 embedding 目标所需字段

在 `_execution_target` 的**两个 SELECT**（assignment 分支、scene_default 分支）中补选：
`m.version model_version, m.embedding_dimension`。仅新增键，不影响既有消费者
（`_client_for_gateway` / `managed_chat*` / `managed_embeddings` 只读已知键）。

### 2. 新增公共访问器

`ModelGovernanceService.embedding_target(kb_id) -> dict | None`：
```python
async def embedding_target(self, kb_id: str) -> dict[str, Any] | None:
    return await self._execution_target(kb_id, Workflow.EMBEDDING, "embedding")
```
（薄封装；语义、优先级、审计与检索路径完全一致。）

### 3. embed 任务改用该访问器（`infrastructure/tasks/ingestion.py`）

- 删除对 `ima.kb_profile_assignments` 的直查。
- 在具备真实 `kb_id` 后，用 `ModelGovernanceService(engine, settings).embedding_target(str(kb_id))` 解析。
- 分流：
  - `kb_id` 缺失 → `failed(..., "DOCUMENT_NOT_FOUND")`（保持）。
  - 解析结果为 `None` → `failed(..., "NO_ASSIGNMENT")`（既有语义）。
  - 结果含 `reason` → `failed(..., row["reason"])`（如 `UNAVAILABLE`；对齐 "
    有 assignment 但 join 不通" 的既有不可用语义）。
  - 否则取 `model_id = row["model_id"]`、`model_version = row["model_version"]`、
    `dimension = row["embedding_dimension"]`。
- 维度校验、chunk 写入使用的 `model_id/model_version/embedding_dimension` 改为来自解析结果，
  其余向量校验（长度一致、有限数、维度唯一）保持不变。
- 注意事务边界：解析通过 service（自管连接）进行，避免在持锁事务内做外部解析。

## 权衡与备选

- **备选 A：只把直查改成「直查 UNION 场景默认」的 SQL** —— 复制了 `_execution_target` 的复杂
  JOIN 与优先级规则，易与检索路径漂移，弃。
- **备选 B：让 `managed_embeddings` 连带返回目标行** —— 改公共方法签名，影响面更大，弃。
- **选定**：解析器补字段 + 薄访问器 + embed 改用它。单一解析来源，检索与摄入天然一致。

## 兼容与回滚

- 无迁移、无 OpenAPI 变更、无新依赖。
- 行为变化：无 KB 分配但设了场景默认 embedding 的 KB，摄入从「永远失败」变为「成功向量化」。
  有 KB 分配时行为不变。
- 回滚：`git revert`。

## 测试策略

- postgres 用例（新增于 `tests/integration/test_postgres_ingestion_state.py` 或新文件）：
  1. 无 KB 分配 + 场景默认 embedding（seed 一个 enabled embedding 模型 + scene_default）→
     `embedding_target` 返回该模型（含 version/dimension）。
  2. 有 KB 分配 → 仍返回分配模型（优先）。
  3. 都无 → `None`。
  4. 场景默认模型禁用 → 返回 `reason='UNAVAILABLE'`（不伪装可用）。
  - 断言点：解析结果的 `model_id/model_version/embedding_dimension/reason`。
- 单测：确认 `embed` 源码不再直查 `kb_profile_assignments`（替换既有文本断言风格，
  `tests/unit/test_ingestion.py` 已有同类断言可扩展）。
- 静态：`ruff`、`mypy`。
- 手动（dev）：给「场景配置 → 向量化」选 `BAAI/bge-m3` 保存；对一个无 KB 分配的知识库上传文档 →
  文档应走到 `file_state='ready'`，chunk 落库 `model_id`/`embedding_dimension` 正确。
