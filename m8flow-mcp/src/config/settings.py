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

    # Token lifecycle
    token_refresh_margin: int = 30  # refresh ROPC token this many seconds before expiry

    # JWT verification
    authz_server_public_key_path: str | None = None

    # OIDC configuration
    oidc_config_url: str | None = None
    required_scopes: str = "openid,profile,email"
    verify_id_token: bool = True

    # OIDCProxy (browser-based login for remote/HTTP mode)
    mcp_oidc_base_url: str | None = None  # public base URL of this MCP server
    mcp_oidc_issuer_url: str | None = None  # defaults to base URL when unset
    mcp_oidc_redirect_path: str = "/oauth/callback"
    mcp_oidc_require_consent: bool = False

    # Secrets
    allow_secret_value_read: bool = False  # gate the show-value tool (UI hides it too)

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
    def required_scopes_list(self) -> list[str]:
        """Parse the comma/space-separated required scopes into a list."""
        return [s for s in self.required_scopes.replace(",", " ").split() if s]

    @property
    def oidc_base_url(self) -> str:
        """Public base URL used by OIDCProxy for OAuth callbacks/metadata."""
        return (self.mcp_oidc_base_url or f"http://localhost:{self.port}").rstrip("/")

    @property
    def oidc_issuer_url(self) -> str:
        """Issuer URL advertised in OAuth metadata (defaults to base URL)."""
        return (self.mcp_oidc_issuer_url or self.oidc_base_url).rstrip("/")

    @property
    def has_oidc_client(self) -> bool:
        """True when a confidential Keycloak client is configured for browser login."""
        return bool(self.client_id and self.client_secret)

    @property
    def has_ropc_credentials(self) -> bool:
        """True when username/password are configured for ROPC auto-login."""
        return bool(self.keycloak_username and self.keycloak_password)

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
