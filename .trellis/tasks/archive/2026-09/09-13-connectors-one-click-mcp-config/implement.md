# Implement: 一键 MCP 配置

按序执行，每步后跑对应验证。遵循 spec：backend `oauth-mcp-contracts.md` / `error-handling.md`，frontend `ux-design-language.md` / `identity-admin-contracts.md` / `quality-guidelines.md`。

## 1. 后端：凭据直通 Bearer

- [ ] 1.1 仓储层（`backend/src/ima/infrastructure/oauth.py`）：按 digest 查未撤销未过期凭据 + 关联 principal 的方法（不存在则新增，复用 `_token_digest`）。
- [ ] 1.2 `McpAuthorizationService.authenticate_bearer`（`backend/src/ima/application/oauth.py`）：access token 未命中 → 走凭据路径（校验、CIDR、限流、McpActor、审计 `mcp.credential.direct_auth`）。
- [ ] 1.3 验证并发租约对 credential.id 的兼容（见 design.md B2），必要时调整 source 计算。
- [ ] 1.4 契约/单元测试 + PostgreSQL 集成测试（design.md B4）。
- 验证：`cd backend && uv run pytest tests/unit tests/contract -q`；集成测试若 Docker 可用：`uv run pytest tests/integration/test_postgres_oauth.py -q`。

## 2. 前端：连接器页面重做

- [ ] 2.1 替换"服务访问"卡片为"MCP 配置"卡片（按钮 → 创建 → 提示条 + 客户端切换 + 代码块 + 复制）。
- [ ] 2.2 密钥扁平列表 + 撤销（`revokeServicePrincipal`）+ 空态/加载态/错误态。
- [ ] 2.3 删除旧表单相关代码与样式；术语清理。
- [ ] 2.4 新增 ConnectorsPage vitest 组件测试。
- 验证：`bun run test:unit`、`bun test`、`bunx vue-tsc --noEmit -p tsconfig.json`、`bun run lint`。

## 3. 收尾

- [ ] 3.1 `bun run build` 通过。
- [ ] 3.2 全量质量检查（两包 spec 的 Quality Check 段）。
- 回滚点：见 design.md「回滚」。

## 注意

- secret 不落 localStorage/sessionStorage；页面刷新后不可再见完整值。
- 审计与错误响应不得回显 secret、query 或 credential 明文。
- OAuth 端点错误保持 OAuth JSON 形态；`/mcp` 401 仍带 `www-authenticate` challenge。
