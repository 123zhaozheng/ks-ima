# 后端：仅场景级模型 + 自动构建检索索引

## 背景

两件事叠加导致「配置了模型也无法正常提问」：

1. **仍存在 KB 级 profile 分配**：`model_governance` 的解析以 `ima.kb_profile_assignments` 为主路径，
   场景默认只是「无分配时的回退」。前端已无 per-KB 分配入口（09-09 任务删除），但后端仍保留该概念、
   接口与表，语义上让管理员误以为还要逐库分配。
2. **向量检索索引从不构建**：`SearchService._vector_target` 要求存在绑定确切 embedding 模型的
   `ima.chunk_search_indexes` active 记录；构建接口 `POST /knowledge-bases/{kb_id}/search-indexes/build`
   存在，但**前端无入口、摄入完成后也不自动构建**。于是文档即使 `ready`，提问仍必然
   `409 REINDEX_REQUIRED`。

## 目标

1. **彻底移除 KB 级模型分配**：检索与摄入一律使用**场景默认**；删除 `kb_profile_assignments`
   表、接口、契约、相关代码与测试。
2. **自动维护检索索引**：摄入向量化完成后自动构建/刷新对应 KB 的精确模型向量索引，使
   `grounded ask` 无需人工干预即可工作；对「已有 ready chunk 但缺 active 索引」的库自愈。

## 需求与约束

- 解析唯一来源：所有运行时模型解析（chat/embedding/rerank）都来自 `scene_defaults` 对应的
  capability profile（`_execution_target` 改为只查场景默认）。KB 参数保留用于审计/日志。
- 语义：
  - 场景未配置对应模型 → `NO_ASSIGNMENT`（保持既有错误码语义）。
  - 场景配置了但模型不可用（禁用/网关下线）→ `UNAVAILABLE`，不伪装可用。
  - 摄入 embed 阶段：无场景 embedding → `NO_ASSIGNMENT`；不可用 → 该 reason。
- 删除 KB 分配：迁移 drop `ima.kb_profile_assignments`（可 downgrade 重建），删除相关 API
  （`/knowledge-bases/{id}/profile-assignments*`）、契约 DTO、`assign/remove_assignment` 服务方法、
  生成的 OpenAPI/前端类型，并更新全部引用与测试。
- 索引：
  - 现有 `build_vector_index` 的构建内核抽为**不依赖 actor 授权**的可复用方法，供 worker 调用；
    HTTP 路由仍保留 owner 授权。
  - embed 阶段成功后（或索引 reconcile 时）为 KB 构建/刷新精确模型索引。
  - 对「KB 有 ready chunk 但无 active 索引」的库，worker reconcile 周期内自愈重建。
  - 索引维度/模型/版本必须与场景默认 embedding 解析结果一致。
- 不新增前端 UI（KB 分配入口本就已移除）；不改上传/下载/预览/取消/重试语义。
- 若新增 postgres 用例，同步更新 `backend/tests/conftest.py` 的精确计数。

## 验收标准

- [ ] `grep -r kb_profile_assignments backend/src` 无残留；表被迁移删除；OpenAPI 不再有
      profile-assignments 路径。
- [ ] 仅配置场景默认（chat/embedding/rerank），一个无任何「分配」的知识库：上传文档 → `ready`
      → **自动出现 active 向量索引** → `POST /knowledge-bases/{id}/ask` 成功返回（不再 REINDEX_REQUIRED）。
- [ ] 已有 ready chunk 但缺索引的库，worker reconcile 后自愈（可用探针构造验证）。
- [ ] 场景未配置 embedding → 摄入失败 `NO_ASSIGNMENT`；场景模型禁用 → `UNAVAILABLE`。
- [ ] `pytest -m postgres` 相关用例通过；`ruff`/`mypy` 通过；OpenAPI 漂移检查通过。
- [ ] spec 更新（`model-governance-contracts.md`、`search-grounded-ask-contracts.md`、
      `object-storage-ingestion-contracts.md`）。

## 非目标

- 不新增 KB 级覆盖能力（明确不做）。
- 不改场景配置的 UI（已存在）。
- 不重构 HNSW 索引实现或检索融合算法。
- 不处理工作区中其它未提交改动。
