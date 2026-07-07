"""MCP tools for M8Flow secrets management.

Provides tools to:
- List all secrets (names only, no values)
- Get secret metadata
- Get secret value (sensitive operation)
- Create new secrets
- Update existing secrets
- Delete secrets

⚠️  SECURITY NOTE:
Secrets are encrypted at rest in the backend and are tenant-isolated.
Secret values should only be retrieved when absolutely necessary.
Never log or display secret values in plain text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token
from src.utils.logging import get_logger
from src.utils.url import quote_path_segment

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()


def register_secret_tools(mcp: FastMCP) -> None:
    """Register secrets management tools with MCP server.

    Provides 6 tools for managing secrets:
    - list_secrets: List all secrets (names only)
    - get_secret: Get secret metadata (no value)
    - get_secret_value: Get actual secret value (⚠️  sensitive)
    - create_secret: Create new secret
    - update_secret: Update secret value
    - delete_secret: Delete secret

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_secrets",
        description="List all secrets available in the current tenant (names only, no values)",
    )
    async def list_secrets(
        page: int = 1,
        per_page: int = 100,
    ) -> dict[str, Any]:
        """List all secrets in the current tenant.

        Returns secret names, owners, and timestamps.
        Secret values are NOT included for security reasons.

        Args:
            page: Page number (default: 1)
            per_page: Results per page (default: 100, max: 1000)

        Returns:
            {
                "results": [
                    {
                        "id": 1,
                        "key": "SMTP_PASSWORD",
                        "username": "admin@example.com",
                        "created_at_in_seconds": 1703001234,
                        "updated_at_in_seconds": 1703005678,
                        "tenantId": "tenant-123",
                        "tenantName": "My Organization"
                    }
                ],
                "pagination": {
                    "count": 10,
                    "total": 45,
                    "pages": 5
                }
            }

        Security:
            - Only returns secret names, never values
            - Tenant-isolated (only see secrets in your tenant)
            - Requires 'read-secrets' permission

        Example:
            # List first page of secrets
            secrets = list_secrets()

            # List specific page
            secrets = list_secrets(page=2, per_page=50)
        """
        token = get_auth_token()

        try:
            params = {"page": page, "per_page": per_page}
            result = await client.get("/secrets", token, params=params)

            # Format output
            if "results" in result:
                output = f"# 🔐 Secrets (Page {page})\n\n"
                output += f"**Total Secrets:** {result.get('pagination', {}).get('total', 0)}\n"
                output += f"**Showing:** {len(result['results'])} secrets\n\n"

                if result["results"]:
                    output += "## Available Secrets\n\n"
                    for secret in result["results"]:
                        key = secret.get("key", "unknown")
                        user = secret.get("username", "unknown")
                        tenant = secret.get("tenantName", secret.get("tenantId", ""))

                        output += f"### `{key}`\n"
                        output += f"- **Created by:** {user}\n"
                        if tenant:
                            output += f"- **Tenant:** {tenant}\n"
                        output += "\n"

                    output += "---\n"
                    output += "💡 Use `get_secret_value(key)` to retrieve the actual secret value\n"
                else:
                    output += "_No secrets found_\n"

                logger.info(f"Listed {len(result['results'])} secrets")
                return output

            return result

        except Exception as e:
            logger.error(f"Failed to list secrets: {e}", exc_info=True)
            return f"❌ Error listing secrets: {str(e)}"

    @mcp.tool(
        name="get_secret",
        description="Get secret metadata without the actual value (safe operation)",
    )
    async def get_secret(key: str) -> str:
        """Get secret metadata without revealing the value.

        This is a safe operation that returns information about a secret
        without exposing the actual secret value.

        Args:
            key: Secret key/name (e.g., "SMTP_PASSWORD")

        Returns:
            Secret metadata including creator and timestamps

        Security:
            - Does NOT return the secret value
            - Use get_secret_value() if you need the actual value
            - Tenant-isolated

        Example:
            # Check if secret exists and who created it
            info = get_secret(key="SMTP_PASSWORD")
        """
        token = get_auth_token()

        try:
            result = await client.get(f"/secrets/{quote_path_segment(key)}", token)

            # Format output
            output = f"# 🔐 Secret: `{key}`\n\n"
            output += f"**ID:** {result.get('id')}\n"
            output += f"**Key:** {result.get('key')}\n"
            output += f"**Created by:** {result.get('username', 'User ID ' + str(result.get('user_id')))}\n"

            created = result.get("created_at_in_seconds")
            updated = result.get("updated_at_in_seconds")
            if created:
                output += f"**Created:** {created}\n"
            if updated:
                output += f"**Updated:** {updated}\n"

            tenant_name = result.get("tenantName", result.get("tenantId"))
            if tenant_name:
                output += f"**Tenant:** {tenant_name}\n"

            output += "\n---\n"
            output += "⚠️  **Note:** This response does not include the secret value.\n"
            output += "Use `get_secret_value(key)` to retrieve the actual value.\n"

            logger.info(f"Retrieved metadata for secret: {key}")
            return output

        except Exception as e:
            logger.error(f"Failed to get secret {key}: {e}", exc_info=True)
            if "404" in str(e) or "not found" in str(e).lower():
                return f"❌ Secret '{key}' not found"
            return f"❌ Error getting secret: {str(e)}"

    @mcp.tool(
        name="get_secret_value",
        description="⚠️  SECURITY SENSITIVE: Get the actual secret value (decrypted)",
    )
    async def get_secret_value(key: str) -> str:
        """Get the actual secret value (decrypted).

        ⚠️  WARNING: SECURITY SENSITIVE OPERATION
        This returns the actual secret value in plain text.
        Only use when absolutely necessary.
        Never log, display, or store the returned value.

        Args:
            key: Secret key/name (e.g., "SMTP_PASSWORD")

        Returns:
            Secret value (decrypted)

        Security:
            - Returns decrypted secret value
            - Use with extreme caution
            - Never display value to users
            - Primarily for programmatic use (connector config)

        Example:
            # Get secret value for connector configuration
            value = get_secret_value(key="SMTP_PASSWORD")

            # Use in connector config (don't display!)
            # connector_config = {"password": value}
        """
        token = get_auth_token()

        try:
            result = await client.get(f"/secrets/show-value/{quote_path_segment(key)}", token)

            value = result.get("value", "")

            output = f"# 🔐 Secret Value: `{key}`\n\n"
            output += "⚠️  **SECURITY WARNING:**\n"
            output += "- This response contains the actual secret value\n"
            output += "- Do not log, display, or store this value insecurely\n"
            output += "- Use only for connector configuration\n\n"
            output += "---\n\n"
            output += f"**Key:** `{key}`\n"
            output += f"**Value:** `{value}`\n\n"
            output += "---\n"
            output += '💡 Reference this secret in workflows using: `"M8FLOW_SECRET:{key}"`\n'

            logger.info(f"Retrieved secret value for: {key}")
            return output

        except Exception as e:
            logger.error(f"Failed to get secret value for {key}: {e}", exc_info=True)
            if "404" in str(e) or "not found" in str(e).lower():
                return f"❌ Secret '{key}' not found"
            return f"❌ Error getting secret value: {str(e)}"

    @mcp.tool(
        name="create_secret",
        description="Create a new secret for connector authentication or configuration",
    )
    async def create_secret(key: str, value: str) -> str:
        """Create a new secret.

        Secrets are encrypted at rest and tenant-isolated.
        Use secrets for connector authentication (passwords, tokens, API keys).

        Args:
            key: Secret name (e.g., "SMTP_PASSWORD", "SLACK_TOKEN")
            value: Secret value (will be encrypted automatically)

        Returns:
            Created secret metadata

        Security:
            - Value is encrypted before storage
            - Secret is scoped to current tenant
            - Key must be unique within tenant
            - Requires 'update-secrets' permission

        Example:
            # Create SMTP password secret
            create_secret(
                key="SMTP_PASSWORD",
                value="myP@ssw0rd123"
            )

            # Create Slack token
            create_secret(
                key="SLACK_BOT_TOKEN",
                value="xoxb-1234567890-abcdefghijk"
            )
        """
        token = get_auth_token()

        try:
            data = {"key": key, "value": value}
            result = await client.post("/secrets", token, data=data)

            output = f"# ✅ Secret Created: `{key}`\n\n"
            output += f"**ID:** {result.get('id')}\n"
            output += f"**Key:** {result.get('key')}\n"
            output += f"**Created:** {result.get('created_at_in_seconds')}\n\n"
            output += "---\n\n"
            output += "## Next Steps:\n\n"
            output += "1. Use in connector configuration:\n"
            output += f'   - Reference as: `"M8FLOW_SECRET:{key}"`\n'
            output += "2. View secret list:\n"
            output += "   - Use: `list_secrets()`\n"
            output += "3. Retrieve value:\n"
            output += f'   - Use: `get_secret_value(key="{key}")`\n\n'
            output += "⚠️  **Security:** Value is encrypted and stored securely.\n"

            logger.info(f"Created secret: {key}")
            return output

        except Exception as e:
            logger.error(f"Failed to create secret {key}: {e}", exc_info=True)
            if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                return f"❌ Secret '{key}' already exists. Use `update_secret()` to change the value."
            if "403" in str(e) or "forbidden" in str(e).lower():
                return "❌ Permission denied. You need 'update-secrets' permission to create secrets."
            return f"❌ Error creating secret: {str(e)}"

    @mcp.tool(
        name="update_secret",
        description="Update an existing secret's value",
    )
    async def update_secret(key: str, value: str) -> str:
        """Update an existing secret's value.

        Args:
            key: Secret name to update
            value: New secret value (will be encrypted)

        Returns:
            Update confirmation

        Security:
            - New value is encrypted before storage
            - Previous value is overwritten
            - Requires 'update-secrets' permission

        Example:
            # Update SMTP password
            update_secret(
                key="SMTP_PASSWORD",
                value="newP@ssw0rd456"
            )
        """
        token = get_auth_token()

        try:
            data = {"value": value}
            await client.put(f"/secrets/{quote_path_segment(key)}", token, data=data)

            output = f"# ✅ Secret Updated: `{key}`\n\n"
            output += "**Status:** Successfully updated\n"
            output += f"**Key:** `{key}`\n\n"
            output += "---\n\n"
            output += "⚠️  **Note:** Previous value has been overwritten.\n\n"
            output += "## Verification:\n\n"
            output += f'- View metadata: `get_secret(key="{key}")`\n'
            output += f'- Verify value: `get_secret_value(key="{key}")`\n'

            logger.info(f"Updated secret: {key}")
            return output

        except Exception as e:
            logger.error(f"Failed to update secret {key}: {e}", exc_info=True)
            if "404" in str(e) or "not found" in str(e).lower():
                return f"❌ Secret '{key}' not found. Use `create_secret()` to create it first."
            if "403" in str(e) or "forbidden" in str(e).lower():
                return "❌ Permission denied. You need 'update-secrets' permission."
            return f"❌ Error updating secret: {str(e)}"

    @mcp.tool(
        name="delete_secret",
        description="Delete a secret permanently",
    )
    async def delete_secret(key: str) -> str:
        """Delete a secret permanently.

        ⚠️  WARNING: This operation cannot be undone.

        Args:
            key: Secret name to delete

        Returns:
            Deletion confirmation

        Security:
            - Permanent deletion
            - Cannot be recovered
            - Requires 'update-secrets' permission

        Example:
            # Delete unused secret
            delete_secret(key="OLD_API_KEY")
        """
        token = get_auth_token()

        try:
            await client.delete(f"/secrets/{quote_path_segment(key)}", token)

            output = f"# ✅ Secret Deleted: `{key}`\n\n"
            output += "**Status:** Successfully deleted\n"
            output += f"**Key:** `{key}`\n\n"
            output += "---\n\n"
            output += "⚠️  **Warning:** This operation cannot be undone.\n\n"
            output += "## Verification:\n\n"
            output += "- List remaining secrets: `list_secrets()`\n"
            output += f'- Confirm deletion: `get_secret(key="{key}")` should fail\n'

            logger.info(f"Deleted secret: {key}")
            return output

        except Exception as e:
            logger.error(f"Failed to delete secret {key}: {e}", exc_info=True)
            if "404" in str(e) or "not found" in str(e).lower():
                return f"❌ Secret '{key}' not found. It may have already been deleted."
            if "403" in str(e) or "forbidden" in str(e).lower():
                return "❌ Permission denied. You need 'update-secrets' permission."
            return f"❌ Error deleting secret: {str(e)}"
