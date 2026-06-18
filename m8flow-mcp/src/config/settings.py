"""Configuration settings for m8flow MCP server."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Server configuration
    server_type: Literal["stdio", "remote"] = "stdio"
    host: str = "0.0.0.0"
    port: int = 8000

    # m8flow Backend API
    m8flow_api_url: str = "http://localhost:6840"
    m8flow_api_timeout: int = 30

    # Keycloak Authentication
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "m8flow"
    client_id: str = "m8flow-mcp"
    client_secret: str | None = None

    # Bearer token (alternative to ROPC)
    m8flow_bearer_token: str | None = None

    # ROPC credentials
    keycloak_username: str | None = None
    keycloak_password: str | None = None

    # JWT verification
    authz_server_public_key_path: str | None = None

    # OIDC configuration
    oidc_config_url: str | None = None
    required_scopes: str = "openid,profile,email"
    verify_id_token: bool = True

    # Multi-tenancy
    default_tenant_id: str | None = None

    # Logging
    log_level: str = "INFO"
    log_format: Literal["json", "text"] = "json"

    # Development
    debug: bool = False
    reload: bool = False

    @property
    def is_remote(self) -> bool:
        """Check if server is running in remote (HTTP) mode."""
        return self.server_type == "remote"

    @property
    def keycloak_token_url(self) -> str:
        """Get Keycloak token endpoint URL."""
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @property
    def keycloak_well_known_url(self) -> str:
        """Get Keycloak OIDC discovery endpoint."""
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/.well-known/openid-configuration"


# Global settings instance
settings = Settings()
