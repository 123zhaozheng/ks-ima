# Design: 一键 MCP 配置

## 总体思路

后端让长期服务凭据（credential secret）可以直接作为 `/mcp` 的 Bearer token；前端把连接器页面的"服务访问"卡片替换为"一键生成 + 配置代码块 + 密钥列表"。创建凭据仍走现有 `POST /api/v1/service-principals`（前端固定参数），无需新 API。

## 后端变更

### B1 `authenticate_bearer` 增加凭据直通路径

文件：`backend/src/ima/application/oauth.py`（`McpAuthorizationService.authenticate_bearer`）+ `backend/src/ima/infrastructure/oauth.py`（仓储）。

现状：`load_access_token(raw)` 未命中即 `invalid_token`。凭据只能经 `exchange_service_credential`（`/oauth/token`）换 600s access token。

变更：`load_access_token` 未命中时，按 `digest = HMAC(secret, token_pepper)` 查 `ima.mcp_credentials`：

- 未命中 → 维持 `invalid_token`。
- 命中则校验：未撤销（`revoked_at IS NULL`）、未过期（`expires_at > now()`）、principal 存在且 `state='active'` 且未过期；scopes 取 principal.scopes（凭据不单独缩窄）。
- 通过后应用与 access-token 路径一致的策略：`_source_allowed(source_ip, principal.cidr_allowlist)`（`network_denied` → 403）、principal 级 `mcp_request` 限流（`rate_limited` → 429）。
- 构造 `McpActor(actor_type='service_principal', principal_id, scopes=principal.scopes, token_id=str(credential.id), source_ip, concurrency_limit=principal.concurrency_limit)`。

### B2 并发租约兼容（实现时验证点）

`acquire_tool_lease` 用 `token_id` UUID + `source_digest`。确认 `ima.mcp_concurrency_leases` 对 `token_id` 是否有指向 `mcp_access_tokens` 的外键：

- 若无 FK（0009 迁移显示租约按 `source_digest` 索引），直接用 credential.id 作为 token_id 即可。
- 若有 FK，则租约 source 改为凭据 digest 体系或按现有 digest 规则写入；不得为直通路径新建 access token 行（避免每次请求写表）。

### B3 审计

直通认证成功/失败追加审计行（动作如 `mcp.credential.direct_auth`），metadata 只含 credential_id / principal_id / 结果，绝不记录 secret。沿用现有 `append_audit` 通道。

### B4 测试

- 契约/单元（`backend/tests/contract/test_oauth_http.py` 或 `test_mcp_transport.py` 层）：有效凭据直通 `/mcp` 返回非 401；撤销/过期/错误凭据 401 且 `www-authenticate` 为 `invalid_token`；CIDR 拒绝为 403。
- PostgreSQL 集成（`backend/tests/integration/test_postgres_oauth.py`）：真实库中创建 principal+凭据 → 直通认证成功 → 撤销凭据 → 立即 401（revocation 即时生效）。

## 前端变更

文件：`src/pages/ConnectorsPage.vue`（仅替换"服务访问"卡片）、复用 `src/utils/mcp-config.ts`（`cursorMcpConfig` / `claudeDesktopMcpConfig` / `prettyJson`，目前无调用方）。

### F1 "MCP 配置"卡片

- 头部：icon `sym_o_key`、标题"MCP 配置"、副标题"一键生成，粘贴到 Cursor / Claude Desktop 即可连接"。
- 主按钮"获取 MCP 配置"，loading 态防重复点击。点击后以固定参数调用 `identityClient.createServicePrincipal`：
  - `displayName`: `MCP 配置 <本地时间 yyyy-MM-dd HH:mm>`
  - `purpose`: `连接器页面一键生成`
  - `ownerUserId`: 当前用户 id
  - `scopes`: 全部四个服务 scope（`mcp:knowledge-bases:read`、`mcp:knowledge:read`、`mcp:knowledge:search`、`mcp:knowledge:write`）
  - `expiresAt`: 现在 + 90 天
  - `rateLimit: 300`、`concurrencyLimit: 10`、`cidrAllowlist: []`
- 成功后展示：
  - 提示条：密钥有效期 90 天、仅显示一次、请妥善保管。
  - 客户端切换（如 `q-btn-toggle`："Cursor / HTTP" 与 "Claude Desktop"）。
  - 只读代码块（`<pre><code>`）：对应 `prettyJson(cursorMcpConfig(secret))` 或 `prettyJson(claudeDesktopMcpConfig(secret))`。
  - 复制按钮复制当前代码块全文（`copyToClipboard` + positive notify）。

### F2 已生成密钥列表

- 扁平列表，数据源为现有 `listServicePrincipals` + `getServicePrincipal`（保持现有加载逻辑）：每行显示 `displayName`、`credential.secretPrefix…`、过期时间（`formatTime`）。
- 行尾仅一个撤销按钮（`sym_o_delete`/`sym_o_key_off`，negative），调用 `revokeServicePrincipal(principal.id)` 整体撤销（一键场景一个 principal 对应一份配置）。
- 空态："暂无已生成的密钥"。loading 态沿用现有文案风格。

### F3 移除

- 服务主体创建表单（`create-grid`、scopes 勾选、`form` reactive）、`oneTime` 横幅、`rotateFirstCredential` / `revokeCredential` / `activeCredential` 等仅服务旧表单的函数与不再使用的样式。
- 术语清理：页面不再出现"服务主体""无人值守智能体"。

### F4 保留不动

- "交互式连接"卡片（OAuth grants）、"加入知识库"卡片、`scopeLabel`/`formatTime`/`copy` 等仍被使用的工具函数。

### F5 测试

- `tests/components/` 新增/扩展 ConnectorsPage vitest：点击生成 → 代码块包含 `/mcp` URL 与 `Bearer <secret>`；切换 Claude Desktop 形态出现 `mcp-remote`；撤销按钮调用 `revokeServicePrincipal`；错误态展示。
- 现有 `src/utils/mcp-config.test.ts`（bun）已覆盖生成器，无需改动。

## 安全权衡（已确认）

凭据直通 Bearer 意味着长期密钥随每次 MCP 请求传输（此前只发往 `/oauth/token`）。内网部署 + 可撤销 + 有审计 + 有 CIDR/限流策略，该权衡成立；这也是"复制粘贴即用"诉求的必然结果（600s token 无法满足）。

## 回滚

- 后端：还原 `authenticate_bearer` 改动即可，凭据回到仅可兑换模式；无 schema 变更。
- 前端：还原 ConnectorsPage.vue 单文件。
