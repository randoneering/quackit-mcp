# quackit

Lightweight session-scoped agent memory core with stdio MCP adapter.

## Features

- **Dual backend** — DuckDB (local file) or Postgres (set `QUACKIT_DATABASE_URL`)
- **Sessions** — start, activate, end, heartbeat with orphan recovery
- **Memories** — save, update (partial), get, search by query/type/content_type
- **Projects** — create, list, search across project scope, consolidate
- **Skills** — save, get, update, delete, list with tag/query filters
- **Transports** — stdio (default) and SSE/HTTP (`quackit serve --transport sse --port 8080`)
- **Metadata** — arbitrary `dict[str, str]` on memories, `title` and `content_type` fields
- **Tool integrations** — pi, Claude Code, Crush, Copilot, Codex CLI, Cursor

## Quick start

```bash
uv sync
uv run pytest -v
uv run python scripts/smoke_test.py
```

## CLI

```bash
quackit --database-path .local/quackit.duckdb start-session
quackit --database-path .local/quackit.duckdb save-memory --session-id <id> --type note --content "hello" --title "hi" --content-type note --metadata '{"key":"val"}'
quackit --database-path .local/quackit.duckdb search-memory "" --session-id <id> --content-type note
quackit --database-path .local/quackit.duckdb update-memory <mem_id> --session-id <id> --content "updated"
quackit --database-path .local/quackit.duckdb save-skill --name "my-skill" --content "instructions"
quackit --database-path .local/quackit.duckdb list-skills --tag trail_of_bits
quackit --database-path .local/quackit.duckdb end-session --session-id <id> --summary "done"
```

## MCP server

```bash
# stdio (default for agent integrations)
uv run python -m quackit.server_stdio

# SSE for remote connections
uv run python -m quackit.server_stdio --transport sse --port 8080
```

## Postgres backend

Set `QUACKIT_DATABASE_URL` (or legacy `AGENT_MEMORY_DATABASE_URL`) to any Postgres connection string. The backend auto-detects and routes accordingly — `--database-path` is ignored when Postgres is active.

```bash
export QUACKIT_DATABASE_URL="postgresql://user:password@host:5432/dbname?sslmode=require"

# Run tests against Postgres
QUACKIT_DATABASE_URL="$URL" uv run pytest -v

# CLI against Postgres
quackit start-session
```

### Neon quick test (no signup)

```bash
DB=$(curl -s -X POST "https://neon.new/api/v1/database" \
  -H "Content-Type: application/json" \
  -d '{"ref": "quackit"}')
URL=$(echo "$DB" | python3 -c "import sys,json; print(json.load(sys.stdin)['connection_string'])")
QUACKIT_DATABASE_URL="$URL" uv run python scripts/smoke_test.py
```

### Any Postgres server

```bash
docker run -d --name pg-memory -e POSTGRES_PASSWORD=password -p 5432:5432 postgres:17
QUACKIT_DATABASE_URL="postgresql://postgres:password@localhost:5432/postgres?sslmode=disable" uv run pytest -v
```

## DuckDB path configuration

Priority: CLI `--database-path` flag > `QUACKIT_DUCKDB_PATH` env var > `.local/quackit.duckdb` (default)

```bash
export QUACKIT_DUCKDB_PATH="/mnt/nfs/quackit.duckdb"
quackit --database-path /mnt/nfs/quackit.duckdb serve
```

The parent directory is created automatically.

## Tool integration

All configs use `uv run python -m quackit.server_stdio` from the repo root. Open the repo in your agent tool — the MCP server is auto-discovered.

| Tool | Config file |
|---|---|
| pi | `.pi/mcp.json` |
| Claude Code | `.mcp.json` |
| Crush (charmbracelet) | `crush.json` |
| GitHub Copilot | `.vscode/settings.json` |
| OpenAI Codex CLI | `.codex/config.toml` |
| Cursor | `.mcp.json` (shared with Claude Code) |

### First flow (any agent)

1. `start_session` — begin a new session
2. `save_memory` — store a note with content, tags, and optional title/content_type/metadata
3. `search_memory` — search stored memories by query, filter by content_type
4. `end_session` — close the session with a summary

### Adding Postgres

```bash
export QUACKIT_DATABASE_URL="postgresql://user:pass@host:5432/db?sslmode=require"
crush   # or pi, claude, codex, etc.
```

### Troubleshooting

1. Test the command: `uv run python -m quackit.server_stdio`
2. Confirm `uv run` works from the repo root
3. Validate config JSON: `uv run python -m json.tool .pi/mcp.json`
4. Restart the agent from the repo root
