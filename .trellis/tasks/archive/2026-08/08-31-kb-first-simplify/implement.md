# 实施计划：知识库一等公民重构

依据 `design.md`。采用并发子智能体分波执行；每个智能体有明确的文件所有权边界，避免冲突。

## 前置约定

- 数据库重置：执行前本地 `DROP SCHEMA ima, jobs CASCADE`（或重建库），`ima migrate` 全新建表。
- 契约循环：后端改完 → `python backend/scripts/export_openapi.py` → 前端重新生成类型 → 前端改造。
- 每个波次结束后运行对应验证命令，失败先修再进下一波。

## Wave 0：基线快照

- [ ] 0.1 记录当前测试基线（后端 `uv run pytest -x -q` 快速过一遍，前端 `npx vitest run`），明确哪些测试预期会因重构删除/重写
- [ ] 0.2 确认数据库可重置（检查 docker-compose / 本地 PG 连接）

## Wave 1：后端核心（3 个并发智能体）

### A. 迁移与领域层（文件所有权：`backend/migrations/**`、`backend/src/ima/domain/**`）
- [ ] 1A.1 改写迁移 0003：`knowledge_bases`、`kb_members(owner/editor/viewer)`、`kb_share_links`、folders/closure 按 `kb_id`；删除 invitations/groups/folder ACL 表
- [ ] 1A.2 改写迁移 0004/0005/0006/0007：删除 tags 表、trash 生命周期，列名 `workspace_id`→`kb_id`，`kb_profile_assignments`
- [ ] 1A.3 改写迁移 0008/0009：`mcp_grants.kb_id` 可空、service principals 用户级、删除 folder_root
- [ ] 1A.4 `domain/authorization.py`：KbRole(owner/editor/viewer)、简化授权矩阵、删除 ACL 相关领域类型；`domain/knowledge.py` 删除 TrashCursor
- 验证：`uv run python -c "import alembic"` 无关，直接跑迁移 `ima migrate` 到空库成功

### B. 授权与身份服务（文件所有权：`backend/src/ima/application/authorization.py`、`application/identity.py`、`infrastructure/db/authorization.py`）
- [ ] 1B.1 `WorkspaceService` → `KbService`：建库/列表/成员管理/文件夹树保留；删除邀请、用户组、ACL、permission_preview、repair 方法
- [ ] 1B.2 新增分享链接：create/list/revoke/accept（peppered digest、可过期、可撤销、幂等加入）
- [ ] 1B.3 `infrastructure/db/authorization.py`：删除 ACL join，改为成员角色一票校验的 SQL
- [ ] 1B.4 `identity.py`：平台能力改名 `knowledge_bases_read/manage`
- 验证：`uv run pytest backend/tests/unit -k "authorization or identity" -q`（先按新语义重写对应测试）

### C. MCP 与 OAuth 用户级授权（文件所有权：`backend/src/ima/application/mcp.py`、`mcp_contracts.py`、`oauth.py`、`infrastructure/oauth.py`、`api/oauth.py`、`api/v1/oauth 相关`）
- [ ] 1C.1 `McpActor` 删除 workspace/folder_root；scope 改名 `mcp:knowledge-bases:read`
- [ ] 1C.2 边界校验改为每调用按目标知识库校验成员资格；写工具要求 editor+；`kb_set_tags` 删除
- [ ] 1C.3 `kb_list_knowledge_bases` 返回用户全量知识库（含 owned/shared 标记）
- [ ] 1C.4 service principal 用户级化；同意页契约删除 workspace 选择
- 依赖：1B 的 KbService 接口（可先按约定接口写，波次末联调）

## Wave 2：后端外围（3 个并发智能体）

### D. 知识/存储/检索/摄取服务与 API（文件所有权：`application/knowledge.py`、`storage.py`、`search.py`、`ingestion.py`、`api/v1/knowledge.py`、`api/v1/search.py`、`infrastructure/tasks/*`）
- [ ] 2D.1 KnowledgeService：删除标签与回收站方法，鉴权简化为成员角色
- [ ] 2D.2 SearchService：按 `kb_id`；历史对话按用户聚合跨库
- [ ] 2D.3 API 端点路径 `/knowledge-bases/{id}/...`；删除 tags/trash 端点

### E. 知识库管理 API 与装配（文件所有权：`api/v1/workspaces.py`→`knowledge_bases.py`、`kb_contracts.py`、`api/v1/admin.py`、`api/v1/model_governance.py`、`api/app.py`、`cli.py`、`scripts/seed_identity_e2e.py`）
- [ ] 2E.1 `/knowledge-bases` CRUD + 成员 + 分享链接端点；删除邀请/组/ACL 端点
- [ ] 2E.2 admin、model_governance、app 装配、种子脚本全部改名
- [ ] 2E.3 重新导出 OpenAPI 并生成前端类型（`export_openapi.py` + 前端生成脚本）

### F. MCP/OAuth HTTP 端点收尾（文件所有权：`api/oauth.py` 剩余、`api/v1/` 中 oauth/grants、service-principals 端点）
- [ ] 2F.1 grants 端点适应用户级授权；service principals 端点删除 workspace 字段
- [ ] 2F.2 后端全量测试重写并通过：`uv run pytest -q`

## Wave 3：前端基础（1 个智能体，串行——交叉文件最多）

### G. 前端改名与导航骨架（文件所有权：`src/router/**`、`src/layouts/AppShell.vue`、`src/stores/**`、`src/api/**`、`src/utils/**`、`i18n/**`）
- [ ] 3G.1 stores/api 客户端跟随新 OpenAPI；`useKbStore`
- [ ] 3G.2 路由重写：删除 `/workspace` 树、`/account*`、`/invitations/:token`；新增 `/join/:token`
- [ ] 3G.3 AppShell 导航精简：Ask / 知识库 / 历史 / 连接器 / 设置（+ 管理台条件入口）
- [ ] 3G.4 i18n 全面更新
- 验证：`npx vue-tsc --noEmit`（或项目等价类型检查）通过

## Wave 4：前端页面（3 个并发智能体）

### H. 知识库主页与加入分享流（文件所有权：`src/pages/KnowledgeWorkspace.vue`→KnowledgeBase、`src/components/FolderTree.vue`、上传/笔记/预览组件、新 `/join/:token` 页面、`src/components/ShareDialog.vue` 等）
- [ ] 4H.1 知识库页：文件夹树 + 文档列表 + 管理面板（成员/分享链接/改名/删除，仅 owner）
- [ ] 4H.2 分享对话框：只读/读写两档 + 链接复制；链接列表 + 撤销
- [ ] 4H.3 `/join/:token` 接受页

### I. 设置单页与 Ask/历史（文件所有权：`src/layouts/SettingsLayout.vue`→SettingsPage、`AccountLayout.vue`/`AccountSecurity.vue` 合并删除、`src/pages/AskHome.vue`、`HistoryPage.vue`、`ConversationView.vue`、`AskComposer.vue`）
- [ ] 4I.1 设置单页三分区（个人资料/安全/偏好）
- [ ] 4I.2 Ask/历史/对话页 kb 化；历史按用户聚合显示所属知识库
- [ ] 4I.3 删除 WorkspaceModels/WorkspaceTags/TrashLayout/WorkspaceOverview 及相关组件

### J. admin 应用与连接器页（文件所有权：`src/admin/**`、`src/pages/WorkspaceConnectors.vue`、`src/pages/OAuthConsentPage.vue`）
- [ ] 4J.1 admin：WorkspacesPage→KnowledgeBasesPage，Users/Models 页改名
- [ ] 4J.2 连接器页：用户级授权说明、grants 列表；service principal 表单删除 workspace/文件夹字段
- [ ] 4J.3 OAuth 同意页：删除 workspace 选择，scope 简化展示

## Wave 5：测试与质量（并发）

- [ ] 5.1 后端测试全面通过（单测 + 契约 + 集成）
- [ ] 5.2 前端组件测试重写通过；`vitest run`
- [ ] 5.3 前端双目标构建通过：`build:front`、`build:admin`
- [ ] 5.4 端到端冒烟：重置数据库 → 注册用户 → 建库 → 分享 → 第二用户加入 → MCP 授权列表知识库（可用 `backend/scripts/seed_identity_e2e.py` + curl）
- [ ] 5.5 e2e Playwright 关键用例更新并通过（如环境允许）

## Wave 6：收尾

- [ ] 6.1 全仓库残留扫描：`workspace` / `工作区` / `invitation` / `folder_acl` / `tags`（语义残留）
- [ ] 6.2 更新 `.trellis/spec/` 相关规范（workspace-authorization-contracts → kb、oauth-mcp-contracts、前端对应规范）与 `docs/`（DESIGN.md、workspace-authorization.md→kb-authorization.md、runbook）
- [ ] 6.3 trellis-check 全量质量检查

## 回滚点

- Wave 1 结束、Wave 2 结束、Wave 3 结束各可作为一个 git 提交回滚点（每个波次末提交一次）。
