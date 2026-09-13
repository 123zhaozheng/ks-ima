# PRD: 简化连接器页面——一键生成可粘贴的 MCP 配置

## 背景与问题

当前连接器页面（`/connectors`）的"服务访问"卡片要求用户理解并手动配置服务主体：名称、用途、有效天数、scope 勾选、轮换等。更严重的是，生成的一次性凭据**不能直接**用作 MCP 客户端的 Bearer token——还需要 `credential_id` + secret 到 `/oauth/token` 兑换 600 秒短时令牌，普通用户无法完成，实测直接粘贴凭据会 401。

用户真实诉求：点一下 → 生成 token → 页面给出完整 MCP 配置 JSON 代码块 → 复制粘贴到其他 agent（Cursor、Claude Desktop 等）即可连接。

## 需求

### R1 一键生成
连接器页面提供单一主按钮（如"获取 MCP 配置"）。点击后前端以固定参数创建服务凭据（无需用户填写任何表单），立即展示结果。

### R2 配置代码块
生成成功后展示只读代码块，内容为完整 MCP 客户端配置 JSON，包含 `/mcp` URL 与 `Authorization: Bearer <token>`，带复制按钮。至少覆盖两种客户端形态：
- 原生 HTTP 客户端（Cursor 等）：`url` + `headers.Authorization`（复用 `src/utils/mcp-config.ts` 的 `cursorMcpConfig`）。
- Claude Desktop（stdio）：`mcp-remote` 桥接形态（复用 `claudeDesktopMcpConfig`）。

### R3 token 直接可用且长期有效
代码块中的 token 必须可以直接作为 `/mcp` 的 Bearer 凭据使用，不需要再兑换；有效期固定 90 天并在页面上明示。到期或被撤销后，客户端请求返回 401。

### R4 最小管理能力
页面保留"已生成密钥"扁平列表：每项显示密钥前缀、过期时间、撤销按钮。撤销后该密钥立即失效。不再出现"服务主体""无人值守""轮换"等术语与表单。

### R5 保留现有区块
- 保留"智能体访问 / 交互式连接"卡片（OAuth 已连接智能体列表及撤销）。
- 保留无知识库时显示的"加入知识库"卡片。

### R6 UI 质量
遵循 `.trellis/spec/frontend/ux-design-language.md` 与现有 `tk-card` 卡片模式；桌面与移动视口均正常；密钥明文只在生成瞬间展示，之后仅显示前缀，且不写入 localStorage/sessionStorage。

## 验收标准

1. 从页面复制的 HTTP 形态配置粘贴到支持 HTTP 的 MCP 客户端后，`initialize` 与 `tools/list` 成功。
2. 撤销某密钥后，用该密钥作 Bearer 的请求返回 401；错误密钥同样 401。
3. 密钥完整值只在生成响应中出现一次；页面刷新后不可再获取完整值。
4. `bun test`、`bun run test:unit`、后端相关 pytest、`bun run lint`、`vue-tsc`、`bun run build` 全部通过。
5. 桌面与移动视口下页面布局无错乱。

## 非目标

- 不改动 OAuth 授权码/交互式连接流程本身。
- 不删除后端服务主体/凭据 API（其他调用方可能依赖）。
- 不引入知识库级授权维度（服务凭据仍是用户级）。
