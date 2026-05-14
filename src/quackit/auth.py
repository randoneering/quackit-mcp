from __future__ import annotations

import os
from typing import Literal
from urllib.parse import urlparse

from fastmcp.server.auth import RemoteAuthProvider, TokenVerifier
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, model_validator


class OAuthConfig(BaseModel):
    issuer_url: AnyHttpUrl
    resource_url: AnyHttpUrl
    scopes: list[str] = Field(default_factory=list)
    audience: str | None = None
    jwks_uri: AnyHttpUrl | None = None
    jwt_algorithm: str = "RS256"
    introspection_url: AnyHttpUrl | None = None
    introspection_client_id: str | None = None
    introspection_client_secret: SecretStr | None = None
    introspection_client_auth_method: Literal[
        "client_secret_basic", "client_secret_post"
    ] = "client_secret_basic"

    @model_validator(mode="after")
    def validate_token_verifier(self) -> "OAuthConfig":
        resource_path = urlparse(str(self.resource_url)).path.rstrip("/")
        if resource_path != "/mcp":
            raise ValueError(
                "QUACKIT_OAUTH_RESOURCE_URL must be the exact MCP endpoint URL "
                "ending in /mcp"
            )
        has_jwks = self.jwks_uri is not None
        has_introspection = self.introspection_url is not None
        if has_jwks == has_introspection:
            raise ValueError(
                "Configure exactly one OAuth token verifier: "
                "QUACKIT_OAUTH_JWKS_URI or QUACKIT_OAUTH_INTROSPECTION_URL"
            )
        if has_introspection and (
            not self.introspection_client_id or self.introspection_client_secret is None
        ):
            raise ValueError(
                "OAuth introspection requires QUACKIT_OAUTH_INTROSPECTION_CLIENT_ID "
                "and QUACKIT_OAUTH_INTROSPECTION_CLIENT_SECRET"
            )
        return self


def _split_scopes(value: str | None) -> list[str]:
    if not value:
        return []
    return [scope for scope in value.replace(",", " ").split() if scope]


def load_oauth_config_from_env() -> OAuthConfig | None:
    issuer_url = os.environ.get("QUACKIT_OAUTH_ISSUER_URL")
    resource_url = os.environ.get("QUACKIT_OAUTH_RESOURCE_URL")
    if not issuer_url and not resource_url:
        return None
    if not issuer_url or not resource_url:
        raise ValueError(
            "OAuth requires both QUACKIT_OAUTH_ISSUER_URL and "
            "QUACKIT_OAUTH_RESOURCE_URL"
        )
    return OAuthConfig(
        issuer_url=issuer_url,
        resource_url=resource_url,
        scopes=_split_scopes(os.environ.get("QUACKIT_OAUTH_SCOPES")),
        audience=os.environ.get("QUACKIT_OAUTH_AUDIENCE"),
        jwks_uri=os.environ.get("QUACKIT_OAUTH_JWKS_URI"),
        jwt_algorithm=os.environ.get("QUACKIT_OAUTH_JWT_ALGORITHM", "RS256"),
        introspection_url=os.environ.get("QUACKIT_OAUTH_INTROSPECTION_URL"),
        introspection_client_id=os.environ.get("QUACKIT_OAUTH_INTROSPECTION_CLIENT_ID"),
        introspection_client_secret=os.environ.get(
            "QUACKIT_OAUTH_INTROSPECTION_CLIENT_SECRET"
        ),
        introspection_client_auth_method=os.environ.get(
            "QUACKIT_OAUTH_INTROSPECTION_CLIENT_AUTH_METHOD",
            "client_secret_basic",
        ),
    )


def _build_token_verifier(config: OAuthConfig) -> TokenVerifier:
    if config.jwks_uri is not None:
        return JWTVerifier(
            jwks_uri=str(config.jwks_uri),
            issuer=str(config.issuer_url).rstrip("/"),
            audience=config.audience,
            algorithm=config.jwt_algorithm,
            required_scopes=config.scopes,
        )
    if config.introspection_url is None:
        raise ValueError("OAuth introspection URL is required")
    return IntrospectionTokenVerifier(
        introspection_url=str(config.introspection_url),
        client_id=config.introspection_client_id or "",
        client_secret=config.introspection_client_secret or "",
        client_auth_method=config.introspection_client_auth_method,
        required_scopes=config.scopes,
    )


def _resource_origin(resource_url: AnyHttpUrl) -> str:
    parsed = urlparse(str(resource_url))
    return f"{parsed.scheme}://{parsed.netloc}"


def build_oauth_provider(config: OAuthConfig) -> RemoteAuthProvider:
    return RemoteAuthProvider(
        token_verifier=_build_token_verifier(config),
        authorization_servers=[config.issuer_url],
        base_url=_resource_origin(config.resource_url),
        scopes_supported=config.scopes,
        resource_name="quackit",
    )
