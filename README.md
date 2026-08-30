# Intranet IMA (Nya AI)

Internal knowledge workspace: directory + Markdown notes + files + Copilot with citations, and an outbound MCP connector for other agents.

Internet features from upstream Nya AI are removed (web search, GitHub plugin, public publish, translation, channels, MCP client plugins, billing).

## Knowledge

- Folders organize notes, files, and chats
- Tags and folder ACLs (inherit / break)
- Full-text search over notes and files
- Copilot uses knowledge search by default and must cite sources

## Connectors

The preferred protected resource is `https://your-host/mcp`. Interactive clients discover OAuth from that URL; service credentials exchange at `/oauth/token` for a short-lived access token before calling it.

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

Tools: `kb_list_dir`, `kb_search`, `kb_ask`, `kb_get_note`, `kb_get_file`, `kb_create_note`, `kb_update_note`, `kb_mkdir`, `kb_set_tags`.

## Development

The Python API in `backend/` is the only backend; the frontend dev servers proxy `/api` to it.

```sh
cp .env.example .env
bun install
bun quasar prepare
docker compose -p ima-dev -f backend/tests/integration/identity-compose.yml up -d # Postgres at 127.0.0.1:55432
cd backend
uv sync --frozen
IMA_DATABASE_URL=postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app uv run ima migrate
IMA_DATABASE_URL=postgresql+asyncpg://postgres:identity-gate-password@127.0.0.1:55432/app uv run uvicorn ima.main:app --reload --port 8000
cd ..
bun dev:front # or: bun dev:admin
```

`docker compose -f docker-compose.example.yml up --build` runs the full deployment example (Postgres, API, worker, web with Caddy).

Point model providers at an intranet OpenAI-compatible gateway. Do not configure public search or crawl endpoints.

See `docs/PRD-intranet-ima.md` for the full product spec.
