# 技术设计：仅场景级模型 + 自动检索索引

## 现状（已核实）

- `ModelGovernanceService._execution_target(kb_id, workflow, operation)`（`application/model_governance.py:2024`）：
  先查 `ima.kb_profile_assignments`（有 assignment 即权威，含不可用 `reason='UNAVAILABLE'`）；无 assignment 行时
  查 `scene_defaults[workflow]`，用相同 profile/version/model/gateway/health JOIN 解析；都无 → `None`。
- `SearchService._profile`（`application/search.py:78`）同样先查 assignment，无则 `_scene_profile()`；
  `_scene_profile` 组合 grounded_ask 的场景默认，并回填 embedding/rerank 场景默认。
- 摄入 embed 阶段已改用 `embedding_target`（= `_execution_target(EMBEDDING)`）。
- `SearchService._vector_target`（`:149`）要求 `ima.chunk_search_indexes` 有 `status='active'` 且
  `model_id/version/dimension` 与 grounded config 的 embedding 模型完全匹配，否则 `409 REINDEX_REQUIRED`。
- `SearchService.build_vector_index(actor, kb_id)`（`:174`）：owner 授权 → 取 `_profile` 的 embedding 模型 →
  校验有 ready chunk → `CREATE INDEX ... hnsw` → 退休旧 active、激活新索引。**唯一调用方是 HTTP 路由**
  `POST /knowledge-bases/{kb_id}/search-indexes/build`（`api/v1/search.py:59`）。**无前端调用**。
- 迁移头：`20260910_0012_scene_defaults`（已提交）。`ima.kb_profile_assignments` 建于 `20260825_0004`。
- 引用 `kb_profile_assignments` 的位置：`application/model_governance.py`(10)、`application/search.py`(2)、
  `api/v1/model_governance.py`(1)、`migrations/20260825_0004`(4)、tests(4 文件)。

## 方案

### A. 移除 KB 级分配（仅场景级）

1. `_execution_target`：删除 assignment 主查询与「assignment 权威」分支；直接解析 `scene_defaults[workflow]`
   （保留相同 JOIN 与 `UNAVAILABLE` 语义）；无场景默认 → `None`。
2. `SearchService._profile`：删除 assignment 查询与 `_scene_profile` 的 assigned 判定；直接返回场景默认组合
   （即现 `_scene_profile` 逻辑），未配置 → `NO_ASSIGNMENT`。
3. 删除 `assign/move/remove_assignment` 服务方法与 `GET/PUT/DELETE .../profile-assignments*` 路由、契约 DTO。
4. 迁移 `20260910_0013_scene_only_models`：`DROP TABLE ima.kb_profile_assignments`；`downgrade` 依据
   `20260825_0004` 的定义重建（结构 + 唯一约束）。
5. 重新生成 OpenAPI 与前端类型（`bun run generate:api`，并同步 `frontend/generated/openapi.json`）。
6. 清理前端 `identity-client.ts` 中 assignment 方法（`listCapabilityAssignments`/`assignCapabilityProfile`/
   `removeCapabilityProfile`）与任何引用；`AuditPage.vue` 若引用则一并清理。
7. 更新/删除引用该表的测试（`test_postgres_model_governance.py`、`test_postgres_search_scene_profile.py`、
   `test_postgres_ingestion_embed_target.py`、`test_ingestion.py`）。

### B. 自动构建向量索引

1. 抽取构建内核：`SearchService.build_vector_index` 拆为
   - `_build_index_core(conn_or_engine, kb_id, model_row)`（无授权、无 `_profile` 依赖，直接以给定模型构建），
   - `build_vector_index(actor, kb_id)`：保留 owner 授权后调用内核。
2. 摄入后自动构建：embed 阶段成功（`file_state='ready'` 之后）为 KB 触发索引构建。
   - 方式：在 worker 内直接调用内核（幂等：`CREATE INDEX IF NOT EXISTS` + 退休/激活），或经
     `JobService` 入队一个 `ima.ingestion.index` 任务。优先**入队任务**以复用重试/可观测性。
   - 需要 KB 的 embedding 模型：通过 `embedding_target(kb_id)` 解析（场景默认）。
   - 若无 ready chunk / 无模型 → 跳过（不报错）。
3. 自愈：`workers/main.py` 的 reconcile 增加「有 ready chunk 但无 active 索引」的 KB 检测 → 入队索引构建。
   （用一条聚合查询：存在 `document_chunks.embedding_status='ready'` 的 KB 且
   `NOT EXISTS` 匹配当前场景 embedding 模型的 active `chunk_search_indexes`。）
4. HTTP 路由保留（owner 手动重建）。

## 权衡与备选

- **备选 A：保留 assignment 表但弃用** —— 与「彻底只留场景级」不符，且留死代码，弃。
- **备选 B：在 ask 请求内惰性建索引** —— 请求路径做 DDL，延迟与锁风险高，弃。
- **备选 C：只在 embed 后建、不做 reconcile** —— 无法救已有 ready-but-unindexed 的库，弃。
- **选定**：删表 + 摄入后入队构建 + reconcile 自愈。

## 兼容与回滚

- 迁移可 downgrade（重建表）；但数据不保留（分配数据本就弃用）。
- 行为变化：不再支持 KB 级分配；无索引的库会自动补齐索引。
- OpenAPI 契约删除若干路径（前端已无调用方，属清理）。
- 回滚：`git revert` + 迁移 downgrade。

## 测试策略

- postgres：
  1. 仅场景默认（无任何分配）下 `_execution_target`/`_profile` 返回场景模型；未配置 → `NO_ASSIGNMENT`；
     模型禁用 → `UNAVAILABLE`。
  2. 摄入一文档后，KB 出现 **active** 索引且 model/version/dimension 与场景默认 embedding 一致。
  3. 构造「ready chunk 无索引」→ reconcile 后索引出现。
  4. 迁移后 `ima.kb_profile_assignments` 不存在；OpenAPI 无 profile-assignments 路径。
- 静态：`ruff`、`mypy`、`pytest tests/contract`（OpenAPI 漂移）、`bun run lint`、`bunx vue-tsc --noEmit`。
- 手动（dev）：清空任何分配 → 设场景默认（chat+embedding+rerank）→ 上传 → 提问成功。
