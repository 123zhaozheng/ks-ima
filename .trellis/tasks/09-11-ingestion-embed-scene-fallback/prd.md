# 让文档摄入的向量化使用场景默认模型回退

## 背景

「场景默认模型」（09-10-scene-model-save，已提交 `630bb82`）的运行时回退只覆盖了检索路径
（`application/search.py`），**没有覆盖文档摄入的向量化阶段**：

- `infrastructure/tasks/ingestion.py` 的 `embed` 任务在调用 `managed_embeddings` 之前，
  **直接查询 `ima.kb_profile_assignments`**（`ingestion.py:296`）来取 embedding 模型与其维度。
- 该直查不包含场景默认回退；因此对一个**没有任何 KB 分配**的知识库，预检 `if not model`
  先行失败（当前错误码 `NO_ASSIGNMENT`），**即使管理员已在「场景配置」里设了全局默认
  embedding 模型**，摄入依然失败。
- 真正执行向量的 `ModelGovernanceService.managed_embeddings` 是**会**回退到场景默认的
  （`_execution_target`），但预检已提前拒绝，永远走不到。

影响：管理员通过 UI 配置了全局 embedding 默认后，上传文档仍无法完成向量化，文档停在
`failed`。而前端**没有**给单个知识库分配模型的入口（`assignCapabilityProfile` 客户端方法
存在但无 UI 调用），所以场景默认是唯一可行的配置途径 —— 正因如此这个缺口是阻塞性的。

## 目标

让摄入的向量化阶段与检索阶段使用**同一套模型解析**（含场景默认回退），从而：
「无 KB 分配 + 已设全局场景默认 embedding」的知识库，上传文档能成功走到 `ready`。

## 需求与约束

- embed 阶段解析 embedding 模型必须与 `managed_embeddings` / `_execution_target` 一致，
  包含：KB 分配（若有）优先，无分配时回退场景默认。
- 语义保持：
  - 既无 KB 分配也无场景默认 → `NO_ASSIGNMENT`（既有语义）。
  - 有解析结果但不可用（模型禁用/网关下线等）→ 对应的不可用语义（`reason`），不伪装成功。
  - KB 存在但文档不存在 → `DOCUMENT_NOT_FOUND`（区分于缺模型）。
- 维度校验保持：写入 chunk 的 `embedding_dimension` 与模型声明维度一致；向量维度不一致仍判失败。
- 不新增迁移、不改 OpenAPI 契约、不新增依赖。
- 不为此新增"per-KB 分配 UI"（属另一议题）。
- 不改上传/下载/预览/取消/重试既有行为。

## 验收标准

- [ ] 无 KB 分配、但已设全局场景默认 embedding 的知识库：上传文档 → `parse/chunk/embed` 全成功、
      文档 `file_state='ready'`，chunk 记录正确的 `model_id` / `embedding_dimension`。
- [ ] 有 KB 分配（且可用）时，仍**优先使用 KB 分配**（回归不变）。
- [ ] 既无分配也无场景默认 → embed 阶段 `failed` 且 `error_code='NO_ASSIGNMENT'`。
- [ ] 场景默认引用的 embedding 模型不可用（禁用/网关下线）→ embed 失败并反映不可用原因，
      不写入伪造成功。
- [ ] 向量维度与模型声明不一致 → 仍判失败（既有校验不丢）。
- [ ] `pytest -m postgres` 相关用例通过（含新增用例）；`ruff` / `mypy` 通过。
- [ ] 更新 spec（`object-storage-ingestion-contracts.md`：摄入与检索共享模型解析）。

## 非目标

- 不新增 KB 级模型分配 UI。
- 不改 `_execution_target` 的解析优先级（KB 分配 > 场景默认）。
- 不重构摄取流水线（parse/chunk/embed 的调度不变）。
- 不处理工作区中其它未提交改动。
