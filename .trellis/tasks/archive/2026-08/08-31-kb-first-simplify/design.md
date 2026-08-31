# 技术设计：知识库一等公民重构

## 总体策略

未上线、数据可丢 ⇒ **不做数据迁移，直接改写迁移历史与代码**。命名映射统一为：

| 旧 | 新 |
|---|---|
| workspace | knowledge base / kb |
| `ima.workspaces` | `ima.knowledge_bases` |
| `workspace_members` | `kb_members`，角色简化为 `owner` / `editor` / `viewer` |
| `workspace_invitations` | 删除，替换为 `kb_share_links` |
| `workspace_groups` / `workspace_group_members` | 删除 |
| `folder_acls` / `folder_acl_entries` | 删除（权限只看成员角色） |
| `workspace_profile_assignments` | `kb_profile_assignments` |
| API `/workspaces/{id}` | `/knowledge-bases/{id}` |
| MCP 工具 `kb_list_workspaces` | `kb_list_knowledge_bases` |

执行分两大步：**(A) 全栈改名**（机械替换 + 迁移改写，行为等价）→ **(B) 功能改造**（分享体系、角色简化、ACL/组/邀请/标签/回收站删除、MCP 用户级授权、前端改版）。这样改名步骤可以用现有测试验证等价性，改造步骤独立可查。

## 1. 数据库（Alembic，改写现有迁移）

- `20260824_0002_identity_platform.py`：`users` 等不动；无工作区内容。
- `20260825_0003_workspace_authorization.py` → 重写为 knowledge base 授权：
  - `ima.knowledge_bases`：`id varchar(32) PK, name, is_active, archived_at, created_by → users, created_at, updated_at`
  - `ima.kb_members`：`PK(kb_id, user_id), role CHECK in ('owner','editor','viewer'), state CHECK in ('active'), version, joined_at`（删除 invited 状态——分享链接接受即 active）
  - `ima.kb_share_links`：`id varchar(32) PK, kb_id FK CASCADE, token_digest varchar(64) UNIQUE, token_salt/pepper（沿用邀请的 peppered digest 模式）, role CHECK in ('editor','viewer'), created_by, expires_at nullable, revoked_at nullable, created_at`
  - `ima.folders`：`kb_id FK`，保留根文件夹 `id = kb_id, is_root = true` 的 CHECK 模式
  - `ima.folder_closure`：`kb_id`
  - 删除：`workspace_invitations`、`workspace_groups`、`workspace_group_members`、`folder_acls`、`folder_acl_entries`、`workspace_authorization_migration`
- `20260825_0005_knowledge_tree.py`：`documents.kb_id`；删除 `tags`、`document_tags` 表；`documents.lifecycle` 简化为只有 `active`（删除 trashed 生命周期、`original_folder_id`、`trashed_at`）。
- `20260825_0006_storage_ingestion.py`、`20260826_0007_search_conversations.py`：`kb_id` 列改名。
- `20260825_0004_model_governance.py`：`kb_profile_assignments`；`model_dependency_index.kb_id`。
- `20260826_0008_oauth_mcp.py`：`mcp_grants.kb_id` 改为可空（null = 用户级全量授权）——新授权一律不写 kb_id；`mcp_service_principals` 删除 `kb_id`（改为用户级，归属 `owner_user_id`），`mcp_credentials.folder_root_id` 删除。
- 部署指引：本地/开发环境 `drop schema ima, jobs cascade` 后 `ima migrate` 重建（写入 docs/runbook）。

## 2. 后端 domain / application

### 2.1 KbService（原 WorkspaceService，`application/authorization.py`）
- 保留核心：建库（事务内建根文件夹 + owner 成员）、列表、成员管理、文件夹树、分享链接。
- **删除**：邀请全流程（issue/accept/revoke invitation、邮件发送）、用户组全部方法、文件夹 ACL（set_acl/acl/acl-subjects/permission_preview/repair_admin 中 ACL 相关）、knowledge_manager 角色。
- 角色默认授权矩阵简化（`domain/authorization.py`）：
  - owner：全部
  - editor：view_metadata, view_content, download, ask, create_child, edit, move, delete
  - viewer：view_metadata, view_content, download, ask
  - 鉴权实现从「成员角色 + 文件夹 ACL 叠加」简化为「成员角色一票决定」，`infrastructure/db/authorization.py` 的 ACL join 全部删除。
- 新增分享链接方法：`create_share_link / list_share_links / revoke_share_link / accept_share_link(token)`（accept：token digest 查找、校验过期/撤销、幂等加入为对应角色；已为成员则不降级不报错）。
- 平台能力 `workspaces_read/manage` 改名 `knowledge_bases_read/manage`（identity.py has_capability）。

### 2.2 KnowledgeService / StorageService / SearchService
- 所有 `workspace_id` 参数改名 `kb_id`。
- KnowledgeService：删除标签（tags）全部方法、删除回收站（trash/restore/TrashCursor）、`_authorize_folder` 简化为成员角色校验。
- SearchService：对话/检索按 `kb_id`；历史对话列表改为按用户聚合（跨库），每条带所属知识库。

### 2.3 MCP / OAuth（用户级授权）
- `McpActor`：删除 `workspace_id` / `folder_root_id`，增加语义「用户级」；`authenticate_bearer` 不再校验单库边界。
- `authorize_oauth_boundary` / `authorize_delegated_boundary` 改为：每次工具调用按目标知识库校验成员资格（human 用 grant 的 scopes；service principal 用自身角色映射，principal 继承 owner 的成员身份做只读/读写判定——principal 写入要求 owner 在该库为 editor+）。
- `kb_list_knowledge_bases`：返回 `KbService.list_knowledge_bases(user_id)` 全量（含 role、owned/shared 标记）。
- 写工具（mkdir/create_note/upload/update_note/move/set_tags→删除该工具?不，set_tags 随 tags 删除、delete）逐个校验目标库角色 ≥ editor；`kb_set_tags` 随标签体系删除。
- `SCOPE_TOOL_MAP` 更新；`mcp:workspaces:read` scope 改名 `mcp:knowledge-bases:read`。
- OAuth 同意页数据：删除 workspace/folder 选择；`/oauth/authorize` 不再接受 workspace_id/folder_root_id 参数。
- `docs/oauth-mcp-coexistence-runbook.md`、`docs/workspace-authorization.md` 更新。

## 3. 后端 API 层

- `api/v1/workspaces.py` → `api/v1/knowledge_bases.py`：前缀 `/knowledge-bases`；删除邀请、组、ACL、permission-preview、repair 端点；新增分享链接端点：
  - `GET/POST /knowledge-bases/{id}/share-links`、`DELETE /knowledge-bases/{id}/share-links/{link_id}`
  - `POST /kb-share-links/{token}/accept`
  - 成员端点保留（列表/改角色（仅 owner 操作）/移除/离开）
- `api/v1/knowledge.py`：tags 端点、trash 端点删除；路径中 `/workspaces/{id}/...` → `/knowledge-bases/{id}/...`。
- `api/v1/model_governance.py`：`workspace_router` → kb；admin 端点路径改名。
- `api/v1/admin.py`：`/admin/workspaces` → `/admin/knowledge-bases`。
- `api/oauth.py` + `OAuthConsentPage` 契约：删除 workspace 选择字段。
- 契约文件改名：`workspace_contracts.py` → `kb_contracts.py`；重新导出 OpenAPI（`backend/scripts/export_openapi.py`）并重新生成前端类型。

## 4. 前端

### 4.1 全栈改名同步（跟随新 OpenAPI 类型）
- `stores/workspace.ts` → `stores/knowledge-base.ts`（`useKbStore`）；`user-data.ts` 的 `lastWorkspaceId` → `lastKbId`。
- `api/knowledge-client.ts`、`api/grounded-client.ts`、`utils/identity-client.ts`、`utils/api-error.ts` 全部跟随新端点。

### 4.2 导航与页面重构（front 应用）
- 侧边栏（`AppShell.vue`）最终结构：
  1. 知识库切换器（顶栏，原 WorkspaceMenuList → KbMenuList：列表/创建/加入入口）
  2. Ask、知识库、历史、连接器、设置（+ 管理台外链，仅管理员角色可见 + 登出）
- 删除：`/workspace` 路由树（WorkspaceOverview/WorkspaceModels/WorkspaceTags）、"Workspace admin" 分组、Trash 菜单项。
- `/kb`（KnowledgeWorkspace → KnowledgeBase 页面）：文件夹树 + 文档列表；知识库管理收纳为页内简洁面板（成员列表、分享链接管理、改名、归档/删除，仅 owner 可见入口）。
- 新增 `/join/:token` 页面（接受分享链接，替换 `/invitations/:token`）。
- 历史页：按用户列出对话，标注所属知识库。
- AskHome/AskComposer/ConversationView：workspace → kb 改名。

### 4.3 设置合并
- 新 `/settings` 单页：卡片分区「个人资料 / 安全 / 偏好」；合并 `SettingsList.vue` + `AccountLayout.vue` + `AccountSecurity.vue` 内容；`/account`、`/account/security` 路由删除；`WorkspaceMenuList` 中的 Account 入口删除。

### 4.4 admin 应用
- `WorkspacesPage.vue` → KnowledgeBasesPage；`AdminDrawer` 导航项改名；`UsersPage`/`ModelsPage` 中的工作区引用改名。

### 4.5 i18n
- `i18n/zh-CN.json` / `zh-TW.json`：71 处工作区文案全部替换为知识库语义；新增分享链接相关文案；删除邀请/标签/回收站残留文案。

## 5. 测试策略

- 后端：先跑现有单测/契约测试发现破坏面 → 按新语义重写（`test_workspace_authorization.py` → `test_kb_authorization.py`；新增分享链接单测/契约测试；MCP 用户级授权契约测试更新）。
- 前端：组件测试（WorkspaceOverview/Models 等删除；KbOverview/Settings 新增）、e2e（oauth-consent.pw.ts 更新）。
- 质量门：后端 `uv run pytest`、前端 `vitest` + `tsc`/build（front 与 admin 双目标）、OpenAPI 契约校验脚本。

## 6. 风险与决策记录

- 迁移历史改写：仅适用于未上线前提；若已有他人依赖旧迁移需沟通。已确认数据可丢。
- MCP 授权从单库绑定改为用户级，安全边界从"授权时限定范围"变为"每次调用校验成员资格"，需保证每个写工具都有角色校验（契约测试覆盖）。
- 标签/回收站删除是用户未明确要求的简化决策，符合"极简、新手友好"总纲；如需保留可在此设计回退。
