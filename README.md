# Intranet IMA (Nya AI)

Internal knowledge workspace: directory + Markdown notes + files + Copilot with citations, and an outbound MCP connector for other agents.

Internet features from upstream Nya AI are removed (web search, GitHub plugin, public publish, translation, channels, MCP client plugins, billing).

## Knowledge

- Folders organize notes, files, and chats
- Tags and folder ACLs (inherit / break)
- Full-text search over notes and files
- Copilot uses knowledge search by default and must cite sources

## Connectors

Workspace owners/admins create API keys at `/workspace/connectors`. Other agents connect with:

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

Tools: `kb_list_dir`, `kb_search`, `kb_ask`, `kb_get_note`, `kb_get_file`, `kb_create_note`, `kb_update_note`, `kb_mkdir`, `kb_set_tags`.

## Development

```sh
cp .env.example .env
bun install
bun quasar prepare
bun dev:db-up
bun dev:server
zero-cache-dev
bun dev:frontend
```

Point model providers at an intranet OpenAI-compatible gateway. Do not configure public search or crawl endpoints.

See `docs/PRD-intranet-ima.md` for the full product spec.
