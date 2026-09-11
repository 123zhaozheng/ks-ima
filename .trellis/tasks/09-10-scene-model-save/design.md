# 技术设计：场景默认模型（scene defaults）

## 现状回顾（已核实）

- 运行时解析链：`managed_chat` / `managed_chat_stream`（workflow 由调用方传入）、`managed_embeddings`（固定 `Workflow.EMBEDDING`）、`managed_rerank`（固定 `Workflow.RERANKING`）→ `_execution_target(kb_id, workflow, operation)` → `ima.kb_profile_assignments` JOIN `capability_profiles` / `capability_profile_versions` / `governed_models` / `model_gateways`。
- 无 assignment → 409 `NO_ASSIGNMENT`（带审计）；有 assignment 但 join 不通 → 503 `UNAVAILABLE`。
- Profile 版本机制：`capability_profile_versions.state ∈ {draft, published, disabled}`，`capability_profiles.current_version` 指向当前发布版本。`create_profile` 建 profile + draft v1；发布后 current_version 递增。
- Profile config 按 workflow 强类型（`parse_profile_config`）：`grounded_ask` 含 chat/embedding/rerank 槽位；`title_generation` / `summarization` 只有 chat；`embedding` 只有 embedding；`reranking` 只有 rerank。
- UI（`ModelsPage.vue`）每张场景卡恰好暴露一个槽位，与上述 workflow→operation 一一对应。

## 方案

新增「场景默认」= 每 workflow 一个系统管理的 capability profile + 一张指针表。

### 数据模型

新表（Alembic migration，schema `ima`）：

```sql
CREATE TABLE ima.scene_defaults (
    workflow   varchar(32) PRIMARY KEY
        REFERENCES ... 无外键到枚举（与 capability_profiles.workflow 同样用 CHECK 约束枚举 5 值）,
    profile_id uuid NOT NULL REFERENCES ima.capability_profiles(id) ON DELETE RESTRICT,
    updated_at timestamptz NOT NULL,
    updated_by varchar(32) REFERENCES ima.users(id)
);
```

- 系统 profile 约定：`business_alias = '场景默认'`（每 workflow 至多一个，受现有 `ux_capability_profiles_workflow_alias` 唯一约束保护）。
- 不复用 `system_settings`（单行列式表，塞 JSON 破坏治理域边界）。

### 服务层（`ModelGovernanceService`）

新增：

- `list_scene_defaults() -> list[dict]`：每 workflow 返回 `{workflow, profileId, profileVersion, modelId}`（modelId 从已发布版本 config 的对应槽位解析；无默认 → 该 workflow 缺省或 modelId=null）。
- `set_scene_default(actor_id, workflow, model_id | None)`：
  1. 校验 model：存在、enabled、capability 匹配 workflow→operation 映射（同 `_execution_target` 既有映射表），否则 422（`MODEL_NOT_FOUND` / `MODEL_DISABLED` / `CAPABILITY_MISMATCH`）。
  2. 找 `(workflow, alias='场景默认')` 的 active profile；没有则 `create_profile`（draft）。
  3. 基于当前发布版本 config 生成新 config（仅替换本 workflow 的目标槽位；`model_id=None` 表示清空槽位），走内部 draft→publish 流程（复用/抽取 `update_profile`+publish 的内部逻辑，保持 config_digest、current_version 语义）。
  4. UPSERT `scene_defaults` 行。
  5. 审计 `model.scene_default.updated`（clear 时 `model.scene_default.cleared`）。
- `clear_scene_default`：可直接由 `set_scene_default(..., None)` 覆盖，UI 暂不暴露独立清除入口（clearable 下拉已可表达）。

修改 `_execution_target`：assignment 主查询无行且 assignment 记录也不存在时，**不再直接 NO_ASSIGNMENT**，先查 `scene_defaults[workflow]` → 用与主查询相同的 JOIN（profile/version/model/gateway/health）解析；

- join 通 → 返回行，附 `source="scene_default"`（供审计/调试区分）；
- 有默认但 join 不通（模型禁用/网关下线等）→ 返回 `reason="UNAVAILABLE"` 行（语义对齐现有 assignment 失效分支）；
- 无默认 → 维持现状 409 `NO_ASSIGNMENT`。

注意：保持「assignment 存在即权威」的现有语义——有 assignment（即使失效）绝不落到场景默认。

### API 层（`model_governance.py` + contracts）

- `GET  /api/v1/admin/scene-defaults` → `{items: [{workflow, profileId, profileVersion, modelId}]}`
- `PUT  /api/v1/admin/scene-defaults/{workflow}` body `{modelId: string | null}` → 200 `{...同上单项}`
- 门禁：`require(request, current, mutate=True)`（PUT），GET `mutate=False`；与相邻 admin 路由一致。
- contracts 放 `model_governance_contracts.py`（`SceneDefaultItem` / `SceneDefaultUpdateRequest`），camelCase alias 与既有契约一致。

### 前端

- `src/utils/identity-client.ts`：新增 `listSceneDefaults()`、`updateSceneDefault(workflow, modelId)`（沿用文件内既有 fetch 封装、错误归一化与 recent-auth 包装约定）。
- `ModelsPage.vue`：
  - `refresh()` 并行拉 `listSceneDefaults`，按 workflow 回填 `sceneState` 对应槽位。
  - `saveSceneConfig(workflow)` 改为真实调用 `updateSceneDefault`：成功 → `notify('已保存','positive')`；失败 → `apiErrorMessage` 负向提示。删除 TODO 注释块与「功能开发中」toast。
  - 保存期间按钮 loading / 防重复提交（与页面其他保存按钮一致的做法）。

## 权衡与备选

- **备选 A：默认值直接存 `system_settings` JSON**——实现最小，但绕开 profile 版本化与治理校验，模型引用不受 RESTRICT 保护，弃。
- **备选 B：不落库，运行时挑「任一 enabled 模型」**——隐式行为不可审计不可控，弃。
- **选定方案**：profile 体系内新增指针表。代价是 set 时要走 draft→publish 流程（复用既有代码路径，复杂度可控），换来版本化、审计、FK 完整性全部继承。

## 兼容与回滚

- 迁移只新增表，可 downgrade（drop）。代码回滚后残留的「场景默认」profile 行无害（只是普通 profile）。
- 行为变化仅一处：无 assignment 且无场景默认 → 与现状完全一致（409）。
- 既有 `pytest -m postgres` 用例必须不回归（特别是 NO_ASSIGNMENT / UNAVAILABLE 语义用例）。

## 测试策略

- 后端：postgres 标记单测——set/list 往返、非法模型 422、回退解析（无 assignment 用场景默认成功）、assignment 优先、默认失效 → UNAVAILABLE、审计行存在。
- 前端：ModelsPage 保存路径的组件测试（mock client），lint/typecheck。
- 手测：管理端保存→刷新回填；用户端无分配 KB 提问走默认模型。
