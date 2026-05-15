<p align="center">
  <img src="assets/quackit.png" alt="quackit" width="200">
</p>

Local-first session memory mcp-server for coding agents, with DuckDB by default and optional Postgres storage! I know there are other options out there, but it felt as if they were more geared towards AI agents within apps or services. I wanted something that would work alongside me, store context, code-snipbits, and even skills that I could reference later. Whether you choose to use DuckDB for project level storage or utilize a remote Postgres server, quackit will be there when you need it.

## Features

- **Local-first** — runs over `stdio` by default. No network required.
- **Storage** — DuckDB by default, or Postgres with `QUACKIT_DATABASE_URL`. ([quack](https://github.com/duckdb/duckdb-quack) protocol already on the road map!) 
- **Sessions** — start, activate, end, heartbeat, recover orphans.
- **Memories** — save, update, get, search by query, type, or content type.
- **Projects** — create, list, group sessions, search project scope, consolidate.
- **Skills** — save, get, update, delete, list reusable records.
- **Transports** — `stdio`, `streamable-http`, `http`, `sse`.
- **Metadata** — tags, `title`, `content_type`, `dict[str, str]` on memories.

## Deployment model

| Use case | Recommended path |
|---|---|
| Local coding agents | `stdio` |
| Local HTTP testing | `streamable-http` on `127.0.0.1` |
| Private self-hosting | `streamable-http` behind your own auth/network controls |

## Install and run locally

Prerequisites: Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/randoneering/quackit-mcp.git
cd quackit
uv sync
```

Run without installing:
```bash
uv run quackit start-session
```

Install globally from checkout:
```bash
uv tool install .
quackit start-session
```

Data directory: `.local/quackit.duckdb` by default.

## Start the MCP server

Use `stdio` for local integration with coding agents. No network port exposed.

```bash
uv run quackit serve --transport stdio
```

## Advanced: run Streamable HTTP, HTTP, or SSE locally

Network transports bind to `127.0.0.1` by default.
`streamable-http` is the recommended HTTP transport; SSE is for legacy clients.

```bash
# Streamable HTTP on localhost
uv run quackit serve --transport streamable-http --port 8000

# HTTP on localhost
uv run quackit serve --transport http --port 8000

# Legacy SSE on localhost
uv run quackit serve --transport sse --port 8000
```

> **Warning:** Non-stdio transports expose memory tools over the network.
> quackit rejects non-localhost bindings unless you pass `--allow-network`.
> Remote HTTP is private/self-hosted only.
> Only use `--allow-network` behind your own network controls.

```bash
uv run quackit serve \
  --transport streamable-http \
  --host 0.0.0.0 \
  --port 8000 \
  --allow-network
```

## Configure storage

### DuckDB

DuckDB is the default backend.
The path priority is:

1. CLI `--database-path`
2. `QUACKIT_DUCKDB_PATH`
3. `AGENT_MEMORY_DUCKDB_PATH`
4. `.local/quackit.duckdb`

```bash
# Use the default path
uv run quackit start-session

# Use an environment variable
export QUACKIT_DUCKDB_PATH="$PWD/.local/dev.duckdb"
uv run quackit start-session

# Override per command
uv run quackit --database-path /tmp/quackit.duckdb start-session
```

The parent directory is created automatically.

### Postgres

Set `QUACKIT_DATABASE_URL` or `AGENT_MEMORY_DATABASE_URL` to use Postgres (`--database-path` is ignored).

```bash
export QUACKIT_DATABASE_URL="postgresql://user:password@host:5432/dbname?sslmode=require"
uv run quackit start-session
```

Local Postgres container:

```bash
docker run -d --name quackit-postgres \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  postgres:17

export QUACKIT_DATABASE_URL="postgresql://postgres:password@localhost:5432/postgres?sslmode=disable"
uv run pytest -v -m postgres
```

## Use the CLI

All commands print JSON.

### Sessions and memories

```bash
SESSION_ID=$(uv run quackit start-session \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

uv run quackit save-memory \
  --session-id "$SESSION_ID" \
  --type note \
  --content "Remember to run pytest before opening a PR" \
  --title "PR checklist" \
  --content-type note \
  --tag workflow \
  --metadata '{"source":"readme"}'

uv run quackit search-memory "pytest" --session-id "$SESSION_ID"
uv run quackit list-sessions --limit 5
uv run quackit end-session --session-id "$SESSION_ID" --summary "README example complete"
```

### Projects

```bash
PROJECT_ID=$(uv run quackit create-project docs --description "Docs work" \
  | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')

uv run quackit start-session --project-id "$PROJECT_ID"
uv run quackit list-projects
uv run quackit list-sessions-by-project "$PROJECT_ID"
```

### Skills

```bash
uv run quackit save-skill \
  --name "review-readme" \
  --description "Checklist for README reviews" \
  --content "Check install, quick start, configuration, and troubleshooting." \
  --tag docs

uv run quackit list-skills --tag docs
uv run quackit list-skills --query readme
```

## MCP tools

The server exposes these tools:

| Area | Tools |
|---|---|
| Projects | `create_project`, `list_projects`, `consolidate_projects` |
| Sessions | `start_session`, `activate_session`, `end_session`, `list_recent_sessions`, `list_sessions_by_project` |
| Memories | `save_memory`, `search_memory`, `get_memory`, `update_memory` |
| Skills | `save_skill`, `get_skill`, `update_skill`, `delete_skill`, `list_skills` |

Safety defaults:

- Tools include MCP annotations for read-only, write, and destructive behavior.
- `list_projects`, `list_sessions_by_project`, `list_skills` accept `limit`.
- `list_skills` returns summaries, omits full content.
- `get_memory` and `get_skill` accept `max_chars`/`offset` for pagination.
  Responses include `content_length`, `truncated`, `next_offset`.
- Treat stored content as untrusted user data. Review as context only.

Typical MCP flow:

1. Call `start_session`.
2. Call `save_memory` with `type`, `content`, and optional `tags`, `title`, `content_type`, or `metadata`.
3. Call `search_memory` with a query.
4. Call `end_session` with a summary.

Example stdio client configuration:

```json
{
  "command": "uv",
  "args": ["run", "quackit", "serve", "--transport", "stdio"]
}
```

## Docker

Build and run the stdio server:

```bash
docker build -t quackit .
docker run --rm -i quackit
```

Persist DuckDB data with a bind mount:

```bash
docker run --rm -i \
  -v "$PWD/.local:/data" \
  quackit
```

Run Streamable HTTP locally from Docker:

```bash
docker run --rm \
  -p 127.0.0.1:8000:8000 \
  quackit serve --transport streamable-http --host 0.0.0.0 --port 8000 --allow-network
```

## Prebuilt images

Prebuilt images are published to GitHub Container Registry:

```bash
docker pull ghcr.io/randoneering/quackit-mcp:latest
```

Tags correspond to git tags (e.g., `v0.1.0` → `ghcr.io/randoneering/quackit-mcp:0.1.0`).
Pin to server in production; `latest` tracks `main`.

### Stdio (default)

```bash
docker run --rm -i ghcr.io/randoneering/quackit-mcp:latest
```

Persist data with a bind mount:

```bash
docker run --rm -i \
  -v "$PWD/.local:/data" \
  ghcr.io/randoneering/quackit-mcp:latest
```

### Streamable HTTP

```bash
docker run --rm \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/randoneering/quackit-mcp:latest \
  serve --transport streamable-http --host 0.0.0.0 --port 8000 --allow-network
```

