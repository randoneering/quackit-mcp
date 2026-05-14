from __future__ import annotations

import asyncio
import json
import os
import socket
from pathlib import Path

import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from quackit.server_stdio import build_server


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _run_streamable_http_test(db_path: Path) -> None:
    os.environ.pop("QUACKIT_DATABASE_URL", None)
    os.environ.pop("AGENT_MEMORY_DATABASE_URL", None)
    server = build_server(database_path=db_path)
    app = server.http_app(transport="streamable-http")
    port = _find_free_port()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uv_server = uvicorn.Server(config)

    async def run_server() -> None:
        await uv_server.serve()

    server_task = asyncio.create_task(run_server())
    await asyncio.sleep(0.5)

    try:
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp") as (
            read,
            write,
            _,
        ):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "create_project",
                    {
                        "name": "streamable-test",
                        "description": "created via Streamable HTTP",
                    },
                )
                data = json.loads(result.content[0].text)
                assert data["name"] == "streamable-test"
                assert data["description"] == "created via Streamable HTTP"

                result = await session.call_tool("list_projects", {})
                projects = json.loads(result.content[0].text)
                assert len(projects) == 1
                assert projects[0]["name"] == "streamable-test"
    finally:
        uv_server.should_exit = True
        await server_task


def test_streamable_http_transport_e2e(tmp_path: Path) -> None:
    asyncio.run(_run_streamable_http_test(tmp_path / "streamable_http_test.duckdb"))
