# 内网 IMA（基于 Nya AI）

内网知识库工作台：目录 + Markdown 笔记 + 文件 + 带引用的 Copilot，并向其他 agent 提供 MCP 连接器。

已去掉公网能力：网页搜索、GitHub 插件、公开发布、翻译、频道、MCP 客户端插件、在线支付。

## 知识库

- 用文件夹组织笔记、文件和对话
- 标签与文件夹权限（继承 / 打断）
- 笔记与文件全文检索
- Copilot 默认走知识库搜索，并应引用资料

## 连接器

工作区 owner/admin 在 `/workspace/connectors` 创建 API Key。其他助手配置：

```json
{
  "mcpServers": {
    "intranet-ima": {
      "url": "https://your-host/api/mcp",
      "headers": { "Authorization": "Bearer ima_..." }
    }
  }
}
```

详见 `docs/PRD-intranet-ima.md`。

## 开发

```sh
cp .env.example .env
bun install
bun quasar prepare
bun dev:db-up
bun dev:server
zero-cache-dev
bun dev:frontend
```

模型请指向内网 OpenAI 兼容网关。
