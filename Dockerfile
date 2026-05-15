FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project
COPY src ./src
RUN uv sync --no-dev --frozen

# Use slim Python without uv — the venv is self-contained at runtime
FROM python:3.12-slim-bookworm

LABEL org.opencontainers.image.source="https://github.com/randoneering/quackit-mcp"
LABEL org.opencontainers.image.description="Local-first session memory for coding agents, backed by DuckDB or Postgres"
LABEL org.opencontainers.image.licenses="GPL-3.0-only"

WORKDIR /app
COPY --from=builder /app /app
RUN groupadd --system quackit \
    && useradd --system --gid quackit --home-dir /app --shell /usr/sbin/nologin quackit \
    && mkdir -p /data \
    && chown -R quackit:quackit /app /data
ENV PATH="/app/.venv/bin:$PATH" \
    QUACKIT_DUCKDB_PATH="/data/quackit.duckdb"
VOLUME ["/data"]
USER quackit
# Port exposed when running in HTTP (streamable-http) transport mode
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD pgrep -f quackit || exit 1
ENTRYPOINT ["quackit"]
CMD ["serve", "--transport", "stdio"]
