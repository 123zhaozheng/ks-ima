# 内网 IMA（基于 Nya AI）

内网知识库工作台：目录 + Markdown 笔记 + 文件 + 带引用的 Copilot，并向其他 agent 提供 MCP 连接器。

已去掉公网能力：网页搜索、GitHub 插件、公开发布、翻译、频道、MCP 客户端插件、在线支付。

## 知识库

- 用文件夹组织笔记、文件和对话
- 标签与文件夹权限（继承 / 打断）
- 笔记与文件全文检索
- Copilot 默认走知识库搜索，并应引用资料

## 连接器

首选受保护资源是 `https://your-host/mcp`。交互式客户端从该地址自动发现 OAuth；服务凭据先在 `/oauth/token` 换取短期访问令牌，再调用该资源。

```json
{
  "mcpServers": {
    "intranet-ima": {
      "url": "https://your-host/mcp",
      "headers": { "Authorization": "Bearer <access-token>" }
    }
  }
}
```

详见 `docs/PRD-intranet-ima.md`。

## 开发

`backend/` 中的 Python API 是唯一后端，前端开发服务器会把 `/api` 代理到它。

```sh
cp .env.example .env
bun install
bun quasar prepare
docker compose -p ima-dev -f backend/tests/integration/identity-compose.yml up -d # Postgres 位于 127.0.0.1:55432
cd backend
uv sync --frozen
IMA_DATABASE_URL=postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app uv run ima migrate
IMA_DATABASE_URL=postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app uv run uvicorn ima.main:app --reload --port 8000
cd ..
bun dev:front # 或：bun dev:admin
```

`docker compose -f docker-compose.example.yml up --build` 会运行完整的部署示例（Postgres、API、worker、带 Caddy 的 web）。

模型请指向内网 OpenAI 兼容网关。
