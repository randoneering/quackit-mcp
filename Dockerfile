FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project
COPY src ./src
RUN uv sync --no-dev --frozen

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
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
EXPOSE 8000
ENTRYPOINT ["quackit"]
CMD ["serve", "--transport", "stdio"]
