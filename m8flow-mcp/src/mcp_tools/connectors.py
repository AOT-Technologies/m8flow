"""MCP tools for M8Flow connector management and operations.

Provides tools to:
- List all available connectors
- Get connector details and operations
- Explore connector parameters and documentation
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from src.api_client import M8flowAPIClient
from src.utils.context import get_auth_token, get_tenant_id
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from fastmcp import FastMCP

logger = get_logger(__name__)
client = M8flowAPIClient()

# Short-lived cache for grouped connectors, keyed by tenant. The service-task
# catalogue changes rarely, so caching avoids refetching + re-parsing on every
# list/get/search/operation call within a session.
_CONNECTOR_CACHE_TTL = 60.0
_connector_cache: dict[str, tuple[float, list[dict]]] = {}


async def _get_grouped_connectors(token: str) -> list[dict]:
    """Fetch service tasks and group them by connector (cached per tenant).

    Args:
        token: Authentication token

    Returns:
        List of connectors with their operations
    """
    cache_key = get_tenant_id() or "_default"
    cached = _connector_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _CONNECTOR_CACHE_TTL:
        return cached[1]

    service_tasks = await client.get("/v1.0/service-tasks", token)

    # Group by connector
    connectors_map: dict[str, dict] = {}
    for task in service_tasks:
        task_id = task.get("id", "")
        if "/" in task_id:
            connector_id, _, operation_name = task_id.partition("/")

            if connector_id not in connectors_map:
                connectors_map[connector_id] = {
                    "id": connector_id,
                    "name": CONNECTOR_NAMES.get(connector_id, connector_id.replace("_", " ").title()),
                    "description": CONNECTOR_DESCRIPTIONS.get(connector_id, ""),
                    "operations": [],
                    "operationCount": 0,
                }

            # Convert camelCase to Title Case (e.g., "GetRequest" -> "Get Request")
            formatted_name = re.sub(r"([A-Z])", r" \1", operation_name).strip()

            operation = {
                "id": task_id,
                "name": formatted_name,
                "rawName": operation_name,
                "description": "",
                "parameters": task.get("parameters", []),
            }

            connectors_map[connector_id]["operations"].append(operation)
            connectors_map[connector_id]["operationCount"] += 1

    connectors = list(connectors_map.values())
    _connector_cache[cache_key] = (time.time(), connectors)
    return connectors


# Connector display names (proper casing that .title() can't derive from the id)
CONNECTOR_NAMES = {
    "http": "HTTP",
    "postgres_v2": "PostgreSQL",
    "slack": "Slack",
    "smtp": "SMTP",
    "salesforce": "Salesforce",
    "stripe": "Stripe",
    "github": "GitHub",
}

# Connector metadata enrichment
CONNECTOR_DESCRIPTIONS = {
    "http": "Make REST API calls (GET, POST, PUT, PATCH, DELETE, HEAD) to external services",
    "postgres_v2": "Execute PostgreSQL database operations (SELECT, INSERT, UPDATE, DELETE, raw SQL)",
    "slack": "Send messages and files to Slack channels and users",
    "smtp": "Send emails via SMTP with HTML/text bodies and attachments",
    "salesforce": "Integrate with Salesforce CRM - manage Leads and Contacts",
    "stripe": "Process payments and manage subscriptions via Stripe",
    "github": "Manage GitHub repositories, branches, and pull requests",
}


def register_connector_tools(mcp: FastMCP) -> None:
    """Register all connector-related MCP tools.

    Args:
        mcp: FastMCP server instance
    """

    @mcp.tool(
        name="list_connectors",
        description="List all available M8Flow connectors with their operations count and metadata",
    )
    async def list_connectors() -> str:
        """List all available connectors with summary information.

        Returns:
            Formatted list of all connectors with metadata
        """
        token = get_auth_token()

        try:
            connectors = await _get_grouped_connectors(token)

            if not connectors:
                return "No connectors available"

            # Format response
            output = ["# 🔌 Available M8Flow Connectors\n"]
            output.append(f"**Total Connectors:** {len(connectors)}\n")
            output.append("---\n\n")

            for conn in connectors:
                connector_id = conn.get("id", "unknown")
                name = conn.get("name", connector_id)
                description = conn.get("description", CONNECTOR_DESCRIPTIONS.get(connector_id, ""))
                op_count = conn.get("operationCount", 0)
                icon = conn.get("icon", "🔧")
                docs_url = conn.get("docsUrl", "")

                output.append(f"## {icon} {name} (`{connector_id}`)\n")
                if description:
                    output.append(f"**Description:** {description}\n")
                output.append(f"**Operations:** {op_count}\n")
                if docs_url:
                    output.append(f"**Documentation:** {docs_url}\n")
                output.append("\n")

            output.append("---\n")
            output.append("💡 Use `get_connector` to see operations for a specific connector\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to list connectors: {e}", exc_info=True)
            return f"❌ Error fetching connectors: {str(e)}"

    @mcp.tool(
        name="get_connector",
        description="Get detailed information about a specific connector including all operations and parameters",
    )
    async def get_connector(connector_id: str) -> str:
        """Get detailed information about a specific connector.

        Args:
            connector_id: Connector ID (e.g., 'slack', 'http', 'postgres_v2')

        Returns:
            Formatted connector details with all operations
        """
        token = get_auth_token()

        try:
            connectors = await _get_grouped_connectors(token)

            # Find the connector
            connector = None
            for conn in connectors:
                if conn.get("id") == connector_id:
                    connector = conn
                    break

            if not connector:
                return f"❌ Connector '{connector_id}' not found"

            # Format response
            name = connector.get("name", connector_id)
            description = connector.get("description", CONNECTOR_DESCRIPTIONS.get(connector_id, ""))
            operations = connector.get("operations", [])
            docs_url = connector.get("docsUrl", "")

            output = [f"# 🔌 {name} Connector\n\n"]
            output.append(f"**ID:** `{connector_id}`\n")
            if description:
                output.append(f"**Description:** {description}\n")
            output.append(f"**Total Operations:** {len(operations)}\n")
            if docs_url:
                output.append(f"**Documentation:** {docs_url}\n")
            output.append("\n---\n\n")

            output.append("## Available Operations\n\n")

            for op in operations:
                op_id = op.get("id", "")
                op_name = op.get("name", op.get("rawName", ""))
                op_desc = op.get("description", "")
                params = op.get("parameters", [])

                output.append(f"### {op_name}\n")
                output.append(f"**Operation ID:** `{op_id}`\n")
                if op_desc:
                    output.append(f"**Description:** {op_desc}\n")
                output.append(f"**Parameters:** {len(params)}\n")
                output.append("\n")

            output.append("---\n")
            output.append("💡 Use `get_connector_operation` for detailed parameter information\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to get connector {connector_id}: {e}", exc_info=True)
            return f"❌ Error fetching connector: {str(e)}"

    @mcp.tool(
        name="get_connector_operation",
        description="Get detailed parameters and documentation for a specific connector operation",
    )
    async def get_connector_operation(operation_id: str) -> str:
        """Get detailed information about a specific connector operation.

        Args:
            operation_id: Full operation ID (e.g., 'slack/PostMessage', 'http/GetRequestV2')

        Returns:
            Formatted operation details with parameters and usage examples
        """
        token = get_auth_token()

        try:
            connectors = await _get_grouped_connectors(token)

            # Find the operation
            operation = None
            connector_name = None
            connector_id = None

            for conn in connectors:
                for op in conn.get("operations", []):
                    if op.get("id") == operation_id:
                        operation = op
                        connector_name = conn.get("name")
                        connector_id = conn.get("id")
                        break
                if operation:
                    break

            if not operation:
                return f"❌ Operation '{operation_id}' not found"

            # Format response
            op_name = operation.get("name", operation.get("rawName", ""))
            op_desc = operation.get("description", "")
            params = operation.get("parameters", [])

            output = [f"# ⚙️ {op_name}\n\n"]
            output.append(f"**Operation ID:** `{operation_id}`\n")
            output.append(f"**Connector:** {connector_name} (`{connector_id}`)\n")
            if op_desc:
                output.append(f"**Description:** {op_desc}\n")
            output.append("\n---\n\n")

            if params:
                output.append("## Parameters\n\n")

                for param in params:
                    # Connector-operation params key their name as "id".
                    param_name = param.get("id", param.get("name", "unknown"))
                    param_type = param.get("type", "string")
                    param_required = param.get("required", False)
                    param_desc = param.get("description", "")
                    param_default = param.get("default")

                    req_badge = "**Required**" if param_required else "_Optional_"

                    output.append(f"### `{param_name}`\n")
                    output.append(f"- {req_badge}\n")
                    output.append(f"- **Type:** {param_type}\n")
                    if param_desc:
                        output.append(f"- **Description:** {param_desc}\n")
                    if param_default is not None:
                        output.append(f"- **Default:** `{param_default}`\n")
                    output.append("\n")
            else:
                output.append("_No parameters required_\n\n")

            output.append("---\n\n")
            output.append("## Usage Example\n\n")
            output.append("```\n")
            output.append("1. Add a Service Task to your BPMN diagram\n")
            output.append("2. In M8flow Service Properties, set:\n")
            output.append(f"   - Operator ID: {operation_id}\n")
            output.append("3. Configure required parameters\n")
            output.append('4. Use secrets for sensitive data: "M8FLOW_SECRET:SECRET_NAME"\n')
            output.append("```\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to get operation {operation_id}: {e}", exc_info=True)
            return f"❌ Error fetching operation: {str(e)}"

    @mcp.tool(
        name="search_connectors",
        description="Search connectors by keyword or use case (e.g., 'email', 'database', 'payment')",
    )
    async def search_connectors(query: str) -> str:
        """Search connectors by keyword or use case.

        Args:
            query: Search query (keyword, use case, or connector name)

        Returns:
            Formatted search results
        """
        token = get_auth_token()

        try:
            connectors = await _get_grouped_connectors(token)

            query_lower = query.lower()
            matches = []

            # Search through connectors
            for conn in connectors:
                connector_id = conn.get("id", "")
                name = conn.get("name", "")
                description = conn.get("description", "")

                # Check if query matches connector
                if (
                    query_lower in connector_id.lower()
                    or query_lower in name.lower()
                    or query_lower in description.lower()
                ):
                    matches.append(
                        {
                            "type": "connector",
                            "connector": conn,
                            "operations": [],
                        }
                    )
                    continue

                # Search operations
                matching_ops = []
                for op in conn.get("operations", []):
                    op_id = op.get("id", "")
                    op_name = op.get("name", "")
                    op_desc = op.get("description", "")

                    if query_lower in op_id.lower() or query_lower in op_name.lower() or query_lower in op_desc.lower():
                        matching_ops.append(op)

                if matching_ops:
                    matches.append(
                        {
                            "type": "operations",
                            "connector": conn,
                            "operations": matching_ops,
                        }
                    )

            if not matches:
                return f"No results found for query: '{query}'"

            # Format response
            output = [f"# 🔍 Search Results for '{query}'\n\n"]
            output.append(f"**Found:** {len(matches)} matches\n\n")
            output.append("---\n\n")

            for match in matches:
                conn = match["connector"]
                connector_id = conn.get("id", "")
                name = conn.get("name", "")
                description = conn.get("description", "")
                matched_ops = match.get("operations", [])

                output.append(f"## {name} (`{connector_id}`)\n")
                if description:
                    output.append(f"**Description:** {description}\n")

                if match["type"] == "connector":
                    output.append("**Match:** Full connector match\n")
                    output.append(f"**Total Operations:** {conn.get('operationCount', 0)}\n")
                else:
                    output.append(f"**Matching Operations:** {len(matched_ops)}\n")
                    for op in matched_ops:
                        op_name = op.get("name", "")
                        op_id = op.get("id", "")
                        output.append(f"- {op_name} (`{op_id}`)\n")

                output.append("\n")

            output.append("---\n")
            output.append("💡 Use `get_connector` or `get_connector_operation` for details\n")

            return "".join(output)

        except Exception as e:
            logger.error(f"Failed to search connectors: {e}", exc_info=True)
            return f"❌ Error searching connectors: {str(e)}"
