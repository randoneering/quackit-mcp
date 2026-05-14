from __future__ import annotations

from pathlib import Path

from starlette.testclient import TestClient

import pytest

from quackit.auth import OAuthConfig
from quackit.server_stdio import build_server


def test_oauth_protected_resource_metadata_endpoint(tmp_path: Path) -> None:
    auth_config = OAuthConfig(
        issuer_url="https://auth.example.com",
        resource_url="https://mcp.example.com/mcp",
        scopes=["quackit:read", "quackit:write"],
        jwks_uri="https://auth.example.com/.well-known/jwks.json",
        audience="https://mcp.example.com/mcp",
    )
    server = build_server(
        database_path=tmp_path / "oauth.duckdb",
        auth_config=auth_config,
    )
    app = server.http_app(transport="streamable-http")

    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource/mcp")

    assert response.status_code == 200
    payload = response.json()
    assert payload["resource"] == "https://mcp.example.com/mcp"
    assert payload["authorization_servers"] == ["https://auth.example.com/"]
    assert payload["scopes_supported"] == ["quackit:read", "quackit:write"]
    assert payload["bearer_methods_supported"] == ["header"]


def test_oauth_http_request_without_bearer_gets_claude_challenge(
    tmp_path: Path,
) -> None:
    auth_config = OAuthConfig(
        issuer_url="https://auth.example.com",
        resource_url="https://mcp.example.com/mcp",
        scopes=["quackit:read"],
        jwks_uri="https://auth.example.com/.well-known/jwks.json",
        audience="https://mcp.example.com/mcp",
    )
    server = build_server(
        database_path=tmp_path / "oauth.duckdb",
        auth_config=auth_config,
    )
    app = server.http_app(transport="streamable-http")

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 401
    www_authenticate = response.headers["WWW-Authenticate"]
    assert www_authenticate.startswith("Bearer ")
    assert 'error="invalid_token"' in www_authenticate
    assert (
        'resource_metadata="https://mcp.example.com/.well-known/oauth-protected-resource/mcp"'
        in www_authenticate
    )


def test_oauth_resource_url_must_be_mcp_endpoint() -> None:
    with pytest.raises(ValueError, match="ending in /mcp"):
        OAuthConfig(
            issuer_url="https://auth.example.com",
            resource_url="https://mcp.example.com",
            scopes=["quackit:read"],
            jwks_uri="https://auth.example.com/.well-known/jwks.json",
        )
