# Intranet IMA (Nya AI)

Internal knowledge bases: users own multiple knowledge bases (folders + Markdown notes + files), join others through share links (read-only or read-write), and ask a Copilot that must cite sources. An outbound MCP connector exposes the knowledge to other agents.

Internet features from upstream Nya AI are removed (web search, GitHub plugin, public publish, translation, channels, MCP client plugins, billing).

## Knowledge

- Folders organize notes, files, and chats
- Share links invite collaborators as read-only (viewer) or read-write (editor)
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

Tools: `kb_list_knowledge_bases`, `kb_list_dir`, `kb_get_tree`, `kb_search`, `kb_ask`, `kb_get_note`, `kb_get_file`, `kb_create_note`, `kb_update_note`, `kb_mkdir`, `kb_upload_file`, `kb_move`, `kb_delete`. Authorizations are user-level: an OAuth grant or service principal covers every knowledge base the creating user can access, and write tools require editor membership per knowledge base.

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

See `docs/DESIGN.md` and `docs/kb-authorization.md` for the current design; `docs/PRD-intranet-ima.md` is the historical product spec.
